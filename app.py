import io
import json
import contextlib
import subprocess
import os
from datetime import datetime
from flask import Flask, render_template
from flask_socketio import SocketIO, emit

# --- 初始化 ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key_for_tools!'
socketio = SocketIO(app, cors_allowed_origins="*") # 允许跨域，方便调试

# --- 工具函数 ---

def run_python_code(code):
    """
    安全地执行Python代码并捕获其标准输出。
    """
    # 创建一个字符串流来捕获print()的输出
    string_io = io.StringIO()
    try:
        # 重定向标准输出到我们创建的流
        with contextlib.redirect_stdout(string_io):
            # 在一个受限的全局环境中执行代码
            exec(code, {})
        # 获取捕获到的输出
        result = string_io.getvalue()
        if not result:
            return "[代码已执行，但没有产生任何打印输出]"
        return result
    except Exception as e:
        # 如果代码执行出错，返回错误信息
        return f"[代码执行错误]: {e}"

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
        return output if output else "[命令已执行，但没有输出]"
    except subprocess.CalledProcessError as e:
        # 捕获命令执行失败的情况
        error_message = f"命令执行失败，返回码: {e.returncode}"
        if e.stdout:
            error_message += f"\n--- STDOUT ---\n{e.stdout}"
        if e.stderr:
            error_message += f"\n--- STDERR ---\n{e.stderr}"
        return error_message
    except Exception as e:
        # 捕获其他可能的错误
        return f"[命令执行时发生未知错误]: {e}"


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
        # --- [核心修改] 新增 run_command 工具的路由 ---
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
        emit('tool_result', {'result': str(result), 'request_id': request_id})

    except Exception as e:
        print(f"工具 '{tool_name}' 执行失败: {e}")
        emit('tool_result', {
            'result': f"[工具执行失败]: {e}",
            'is_error': True,
            'request_id': request_id
        })

# --- Flask 路由 ---
@app.route('/')
def index():
    """渲染主页面"""
    return render_template('index.html')

if __name__ == '__main__':
    print("工具箱服务器启动，请在浏览器中访问 http://127.0.0.1:5000")
    # 使用 eventlet 或 gevent 可以获得更好的性能，但对于此示例，默认的 werkzeug 也能工作
    socketio.run(app, port=5000)
