import io
import json
import contextlib
import subprocess
import os
import uuid
import time
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

# --- 初始化 ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key_for_tools!'
socketio = SocketIO(app, cors_allowed_origins="*") # 允许跨域，方便调试

# 内存存储保存的代码（生产环境应使用数据库）
saved_codes_store = {}

# --- 工具函数 ---

def execute_python_code(code):
    """
    执行Python代码并返回详细结果
    """
    start_time = time.time()
    return_code = 0
    output = ""
    error = ""
    
    # 创建一个字符串流来捕获print()的输出
    string_io = io.StringIO()
    try:
        # 重定向标准输出到我们创建的流
        with contextlib.redirect_stdout(string_io):
            # 在一个受限的全局环境中执行代码
            exec(code, {})
        # 获取捕获到的输出
        output = string_io.getvalue()
        if not output:
            output = "[代码已执行，但没有产生任何打印输出]"
    except Exception as e:
        # 如果代码执行出错，返回错误信息
        error = f"[代码执行错误]: {e}"
        return_code = 1
    
    execution_time = time.time() - start_time
    
    return {
        "output": output,
        "error": error,
        "return_code": return_code,
        "execution_time": execution_time
    }

def run_python_code(code):
    """
    安全地执行Python代码并捕获其标准输出。
    """
    result = execute_python_code(code)
    if result["error"]:
        return result["error"]
    return result["output"]

def run_command(command):
    """
    执行一个shell命令并返回其输出。
    警告: 这个函数给予了执行任意shell命令的权限，请确保只在受信任的环境中运行。
    """
    try:
        print(f"Executing command: {command}")
        # 使用 subprocess.run 来执行命令
        # shell=True 允许我们像在终端一样运行命令字符串
        # capture_output=True 捕获标准输出和标准错误
        # text=True 使输出以文本形式返回
        # check=True 如果命令返回非零退出码（表示错误），则会抛出 CalledProcessError
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8' # 明确指定编码以避免乱码
        )
        # 合并标准输出和标准错误（如果有的话）
        output = result.stdout
        if result.stderr:
            output += "\n--- STDERR ---\n" + result.stderr
        return {"result": output, "error": None}
    except subprocess.CalledProcessError as e:
        # 捕获命令执行失败的情况
        error_message = f"命令执行失败，返回码: {e.returncode}"
        if e.stdout:
            error_message += f"\n--- STDOUT ---\n{e.stdout}"
        if e.stderr:
            error_message += f"\n--- STDERR ---\n{e.stderr}"
        return {"result": None, "error": error_message}
    except Exception as e:
        # 捕获其他可能的错误
        return {"result": None, "error": f"[命令执行时发生未知错误]: {e}"}


# --- WebSocket 事件处理 ---

@socketio.on('connect')
def handle_connect():
    """当客户端连接时调用"""
    print('前端 Agent 已连接到工具箱服务器')

@socketio.on('disconnect')
def test_disconnect():
    print('前端 Agent 已断开连接')

@socketio.on('use_tool')
def handle_tool_use(data):
    """
    处理来自前端的工具使用请求。
    这是一个总的入口，根据请求的工具名称分发到不同的函数。
    """
    tool_name = data.get('tool')
    query = data.get('query')
    request_id = data.get('request_id') # 用于让前端匹配响应
    
    print(f"收到工具调用请求: {tool_name}, 查询: '{query}'")
    
    result = None
    try:
        if tool_name == 'run_command':
            result = run_command(str(query))
        elif tool_name == 'run_code':
            result = run_python_code(str(query))
        # 保留原有的其他工具
        elif tool_name == 'time':
            result = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            # 对于 'write_code' 和 'calculator' 等在前端处理或此处未实现的工具
            # 我们假设前端逻辑正确，此处只处理后端实现的工具
            # 如果工具未知，则抛出错误
            raise ValueError(f"未知的后端工具: {tool_name}")

        print(f"工具 '{tool_name}' 执行结果: {result}")
        # 将结果和原始请求ID一起发回
        emit('tool_result', {'result': result, 'request_id': request_id})

    except Exception as e:
        print(f"工具 '{tool_name}' 执行失败: {e}")
        emit('tool_result', {
            'result': {"result": None, "error": f"[工具执行失败]: {e}"},
            'is_error': True,
            'request_id': request_id
        })

# --- Flask 路由 ---

@app.route('/')
def index():
    """渲染主页面"""
    return render_template('index.html')

# 代码管理API
@app.route('/api/save_code', methods=['POST'])
def save_code():
    """保存代码到后端"""
    try:
        data = request.get_json()
        if not data or 'name' not in data or 'code' not in data:
            return jsonify({"error": "缺少必要参数"}), 400
            
        code_id = str(uuid.uuid4())
        saved_codes_store[code_id] = {
            "id": code_id,
            "name": data['name'],
            "code": data['code'],
            "created_at": datetime.now().isoformat()
        }
        return jsonify({"code_id": code_id, "message": "代码保存成功"})
    except Exception as e:
        return jsonify({"error": f"保存代码失败: {str(e)}"}), 500

@app.route('/api/saved_codes', methods=['GET'])
def get_saved_codes():
    """获取已保存的代码列表"""
    try:
        codes = list(saved_codes_store.values())
        return jsonify({"codes": codes})
    except Exception as e:
        return jsonify({"error": f"获取代码列表失败: {str(e)}"}), 500

@app.route('/api/run_saved_code', methods=['POST'])
def run_saved_code():
    """运行已保存的代码"""
    try:
        data = request.get_json()
        if not data or 'code_id' not in data:
            return jsonify({"error": "缺少code_id参数"}), 400
            
        code_id = data['code_id']
        if code_id not in saved_codes_store:
            return jsonify({"error": "代码不存在"}), 404
        
        code = saved_codes_store[code_id]["code"]
        result = execute_python_code(code)
        
        return jsonify({
            "output": result["output"],
            "error": result["error"],
            "return_code": result["return_code"],
            "execution_time": result["execution_time"]
        })
    except Exception as e:
        return jsonify({"error": f"运行保存的代码失败: {str(e)}"}), 500

@app.route('/api/saved_code/<code_id>', methods=['GET'])
def get_saved_code(code_id):
    """获取特定代码的详细信息"""
    try:
        if code_id not in saved_codes_store:
            return jsonify({"error": "代码不存在"}), 404
        
        return jsonify(saved_codes_store[code_id])
    except Exception as e:
        return jsonify({"error": f"获取代码详情失败: {str(e)}"}), 500

@app.route('/api/saved_code/<code_id>', methods=['DELETE'])
def delete_saved_code(code_id):
    """删除已保存的代码"""
    try:
        if code_id not in saved_codes_store:
            return jsonify({"error": "代码不存在"}), 404
        
        del saved_codes_store[code_id]
        return jsonify({"message": "代码删除成功"})
    except Exception as e:
        return jsonify({"error": f"删除代码失败: {str(e)}"}), 500

if __name__ == '__main__':
    print("工具箱服务器启动，请在浏览器中访问 http://127.0.0.1:5000")
    # 使用 eventlet 或 gevent 可以获得更好的性能，但对于此示例，默认的 werkzeug 也能工作
    socketio.run(app, port=5000)
