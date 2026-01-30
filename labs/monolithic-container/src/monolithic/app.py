from flask import Flask, render_template_string, request, jsonify, redirect, url_for
import redis
import json
import os

app = Flask(__name__)

# Connect to Redis (localhost since it's in the same container)
redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

# HTML Template embedded in the application
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Task Manager</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
        .task { padding: 10px; margin: 10px 0; background: #f0f0f0; border-radius: 5px; }
        .task.completed { background: #d4edda; text-decoration: line-through; }
        form { margin: 20px 0; }
        input[type="text"] { padding: 10px; width: 300px; }
        button { padding: 10px 20px; background: #007bff; color: white; border: none; cursor: pointer; }
        .delete-btn { background: #dc3545; margin-left: 10px; }
        .complete-btn { background: #28a745; }
        .stats { background: #e9ecef; padding: 15px; border-radius: 5px; margin: 20px 0; }
    </style>
</head>
<body>
    <h1>Task Manager</h1>
    <div class="stats">
        <strong>Statistics:</strong> {{ total_tasks }} total tasks | {{ completed_tasks }} completed | Server: Monolithic Container
    </div>
    <form action="/tasks" method="POST">
        <input type="text" name="title" placeholder="Enter a new task..." required>
        <button type="submit">Add Task</button>
    </form>
    <h2>Tasks</h2>
    {% for task in tasks %}
    <div class="task {{ 'completed' if task.completed else '' }}">
        <strong>{{ task.title }}</strong>
        <form action="/tasks/{{ task.id }}/toggle" method="POST" style="display:inline;">
            <button type="submit" class="complete-btn">{{ 'Undo' if task.completed else 'Complete' }}</button>
        </form>
        <form action="/tasks/{{ task.id }}/delete" method="POST" style="display:inline;">
            <button type="submit" class="delete-btn">Delete</button>
        </form>
    </div>
    {% endfor %}
    <hr>
    <h3>API Endpoints</h3>
    <ul>
        <li>GET /api/tasks - List all tasks</li>
        <li>POST /api/tasks - Create a task</li>
        <li>GET /api/health - Health check</li>
    </ul>
</body>
</html>
"""

def get_tasks():
    """Retrieve all tasks from Redis"""
    tasks = []
    task_ids = redis_client.smembers('task_ids')
    for task_id in task_ids:
        task_data = redis_client.get(f'task:{task_id}')
        if task_data:
            task = json.loads(task_data)
            task['id'] = task_id
            tasks.append(task)
    return sorted(tasks, key=lambda x: x.get('id', 0))

def get_next_id():
    """Get next task ID"""
    return redis_client.incr('task_counter')

# Web Routes
@app.route('/')
def index():
    tasks = get_tasks()
    total_tasks = len(tasks)
    completed_tasks = len([t for t in tasks if t.get('completed', False)])
    return render_template_string(HTML_TEMPLATE, tasks=tasks,
                                  total_tasks=total_tasks,
                                  completed_tasks=completed_tasks)

@app.route('/tasks', methods=['POST'])
def create_task():
    title = request.form.get('title')
    if title:
        task_id = str(get_next_id())
        task = {'title': title, 'completed': False}
        redis_client.set(f'task:{task_id}', json.dumps(task))
        redis_client.sadd('task_ids', task_id)
    return redirect(url_for('index'))

@app.route('/tasks/<task_id>/toggle', methods=['POST'])
def toggle_task(task_id):
    task_data = redis_client.get(f'task:{task_id}')
    if task_data:
        task = json.loads(task_data)
        task['completed'] = not task.get('completed', False)
        redis_client.set(f'task:{task_id}', json.dumps(task))
    return redirect(url_for('index'))

@app.route('/tasks/<task_id>/delete', methods=['POST'])
def delete_task(task_id):
    redis_client.delete(f'task:{task_id}')
    redis_client.srem('task_ids', task_id)
    return redirect(url_for('index'))

# API Routes
@app.route('/api/tasks', methods=['GET'])
def api_get_tasks():
    return jsonify(get_tasks())

@app.route('/api/tasks', methods=['POST'])
def api_create_task():
    data = request.get_json()
    if data and data.get('title'):
        task_id = str(get_next_id())
        task = {'title': data['title'], 'completed': False}
        redis_client.set(f'task:{task_id}', json.dumps(task))
        redis_client.sadd('task_ids', task_id)
        task['id'] = task_id
        return jsonify(task), 201
    return jsonify({'error': 'Title required'}), 400

@app.route('/api/health', methods=['GET'])
def health_check():
    try:
        redis_client.ping()
        redis_status = 'healthy'
    except:
        redis_status = 'unhealthy'
    return jsonify({
        'status': 'running',
        'redis': redis_status,
        'container_type': 'monolithic'
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
