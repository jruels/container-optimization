# Refactoring Monolithic Containers

## Overview

In this lab, you will explore the challenges of running multiple services in a single "monolithic" container and learn how to refactor it into a multi-container architecture. This lab uses both **Python** and **.NET** examples to demonstrate that these principles apply regardless of technology stack.

By the end of this lab, you will understand:

- **Why** monolithic containers cause operational problems in production
- How to identify services that should be separated
- Techniques for refactoring into multiple containers
- How to use Docker Compose to orchestrate multi-container applications
- The measurable benefits of a microservices-based container architecture

## What is a Monolithic Container?

A monolithic container is a container that runs multiple processes or services within a single image. While this might seem convenient initially, it violates the principle of "one process per container" and introduces several challenges:

| Challenge | Description | Why It Matters |
|-----------|-------------|----------------|
| **Large Image Size** | Including multiple services, dependencies, and tools bloats the image | Slower deployments, more storage costs, larger attack surface |
| **Scaling Difficulties** | Cannot scale individual components independently | If API needs 10 replicas but database needs 1, you waste resources running 10 databases |
| **Single Point of Failure** | If one service crashes, the entire container may fail | A bug in logging shouldn't take down your database |
| **Complex Updates** | Updating one service requires rebuilding and redeploying the entire container | A 1-line Python fix requires rebuilding Redis too |
| **Resource Contention** | Services compete for CPU and memory within the same container | Redis memory spike can OOM-kill your API |
| **Difficult Debugging** | Log management and troubleshooting become complex | Finding one error in 5 interleaved log streams wastes time |
| **Poor Isolation** | Security vulnerabilities in one service can affect others | A compromised API has direct access to your database |

---

## Lab Steps

This lab provides two technology tracks. Choose the one that matches your team's stack, or complete both to see that the patterns are universal.

- **Track A: Python + Redis** - Flask-based task manager
- **Track B: .NET + Redis** - ASP.NET Core minimal API

---

## Track A: Python Monolithic Application

### Step 1: Create the Lab Directory

First, create a directory for this lab and navigate to it:

```console
mkdir -p ~/monolithic-containers && cd ~/monolithic-containers
```

**Why create a dedicated directory?** Isolating lab files prevents conflicts with other projects and makes cleanup straightforward.

Create the application directory structure:

```console
mkdir -p monolithic-python/src
```

### Step 2: Examine the Monolithic Design

We'll work with a simple task management application that consists of three components:

1. **Web Application** - A Flask-based frontend that displays tasks
2. **API Service** - Handles task CRUD operations
3. **Redis** - Stores task data and manages sessions

In our monolithic design, all of these run in a single container using a process manager.

**Why is this problematic?** Each of these components has different:
- Scaling requirements (API may need 10 instances, Redis needs 1)
- Update frequencies (API changes weekly, Redis rarely)
- Resource profiles (Redis is memory-intensive, API is CPU-intensive)
- Failure modes (Redis crash shouldn't kill the API)

### Step 3: Create the Monolithic Application

Create the main application file that contains both the web frontend and API:

```console
cat << 'EOF' > monolithic-python/src/app.py
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
    <h1>Task Manager (Python)</h1>
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
EOF
```

### Step 4: Create the Monolithic Dockerfile

Now create the Dockerfile that packages everything into a single container:

```console
cat << 'EOF' > monolithic-python/Dockerfile
# Monolithic Container - Anti-pattern demonstration
# This container runs multiple services: Redis + Python Web App + Process Manager

FROM ubuntu:22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install ALL dependencies in a single layer (bad practice for demonstration)
RUN apt-get update && apt-get install -y \
    # Python and web dependencies
    python3 \
    python3-pip \
    python3-dev \
    # Redis server
    redis-server \
    # Process manager to run multiple services
    supervisor \
    # Debugging tools (often included unnecessarily)
    curl \
    wget \
    vim \
    htop \
    net-tools \
    iputils-ping \
    # Build tools (not needed at runtime)
    build-essential \
    gcc \
    # Clean up (but damage is done - layer is already large)
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip3 install --no-cache-dir \
    flask==3.0.0 \
    redis==5.0.1 \
    gunicorn==21.2.0 \
    requests==2.31.0

# Create application directory
WORKDIR /app

# Copy application code
COPY src/app.py /app/

# Create supervisord configuration to manage multiple processes
RUN mkdir -p /var/log/supervisor
COPY <<SUPERVISOR_CONF /etc/supervisor/conf.d/supervisord.conf
[supervisord]
nodaemon=true
logfile=/var/log/supervisor/supervisord.log
pidfile=/var/run/supervisord.pid

[program:redis]
command=/usr/bin/redis-server --protected-mode no
autostart=true
autorestart=true
stdout_logfile=/var/log/supervisor/redis-stdout.log
stderr_logfile=/var/log/supervisor/redis-stderr.log
priority=1

[program:webapp]
command=/usr/bin/python3 /app/app.py
directory=/app
autostart=true
autorestart=true
stdout_logfile=/var/log/supervisor/webapp-stdout.log
stderr_logfile=/var/log/supervisor/webapp-stderr.log
priority=2
SUPERVISOR_CONF

# Expose the web application port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# Run supervisord to manage all processes
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
EOF
```

**Why use supervisord?** Docker expects one process per container. When you need multiple processes, you need a process manager like supervisord to:
- Start all processes
- Monitor them for crashes
- Restart failed processes
- Handle signals properly

**This is a red flag** - if you need supervisord, you probably need multiple containers.

### Step 5: Build and Run the Monolithic Container

Build the monolithic container image:

```console
cd ~/monolithic-containers/monolithic-python
docker build -t task-app:monolithic-python .
```

**Why does this take so long?** The build installs:
- An entire Ubuntu base image (~75MB)
- Python runtime and development tools
- Redis server
- Supervisord process manager
- Network debugging tools (vim, htop, curl, wget, net-tools)
- C compiler and build tools

Most of these aren't needed at runtime but are baked into the image forever.

Check the image size:

```console
docker images task-app:monolithic-python
```

**Document this size** - you'll compare it later. Expect 500-600MB.

Run the container:

```console
docker run -d --name monolithic-python -p 5000:5000 task-app:monolithic-python
```

Wait a few seconds for all services to start, then test:

```console
curl http://localhost:5000/api/health
```

You should see output indicating both the app and Redis are running.

---

## Track B: .NET Monolithic Application

If you're following the .NET track, create the equivalent monolithic application here.

### Step 1: Create the Directory Structure

```console
mkdir -p ~/monolithic-containers/monolithic-dotnet/src
cd ~/monolithic-containers
```

### Step 2: Create the .NET Application

```console
cat << 'EOF' > monolithic-dotnet/src/Program.cs
using System.Text.Json;
using StackExchange.Redis;

var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();

// Connect to Redis (localhost since it's in the same container)
var redis = ConnectionMultiplexer.Connect("localhost:6379");
var db = redis.GetDatabase();

app.MapGet("/", () => Results.Content(GetHtmlPage(), "text/html"));

app.MapPost("/tasks", async (HttpRequest request) =>
{
    var form = await request.ReadFormAsync();
    var title = form["title"].ToString();
    if (!string.IsNullOrEmpty(title))
    {
        var taskId = db.StringIncrement("task_counter").ToString();
        var task = new { title, completed = false };
        db.StringSet($"task:{taskId}", JsonSerializer.Serialize(task));
        db.SetAdd("task_ids", taskId);
    }
    return Results.Redirect("/");
});

app.MapPost("/tasks/{id}/toggle", (string id) =>
{
    var taskData = db.StringGet($"task:{id}");
    if (!taskData.IsNullOrEmpty)
    {
        var task = JsonSerializer.Deserialize<Dictionary<string, object>>(taskData!);
        if (task != null)
        {
            var completed = task.ContainsKey("completed") &&
                task["completed"] is JsonElement elem && elem.GetBoolean();
            task["completed"] = !completed;
            db.StringSet($"task:{id}", JsonSerializer.Serialize(task));
        }
    }
    return Results.Redirect("/");
});

app.MapPost("/tasks/{id}/delete", (string id) =>
{
    db.KeyDelete($"task:{id}");
    db.SetRemove("task_ids", id);
    return Results.Redirect("/");
});

app.MapGet("/api/tasks", () =>
{
    var tasks = new List<object>();
    var taskIds = db.SetMembers("task_ids");
    foreach (var taskId in taskIds)
    {
        var taskData = db.StringGet($"task:{taskId}");
        if (!taskData.IsNullOrEmpty)
        {
            var task = JsonSerializer.Deserialize<Dictionary<string, object>>(taskData!);
            if (task != null)
            {
                task["id"] = taskId.ToString();
                tasks.Add(task);
            }
        }
    }
    return Results.Json(tasks);
});

app.MapPost("/api/tasks", async (HttpRequest request) =>
{
    var body = await JsonSerializer.DeserializeAsync<Dictionary<string, string>>(request.Body);
    if (body != null && body.TryGetValue("title", out var title) && !string.IsNullOrEmpty(title))
    {
        var taskId = db.StringIncrement("task_counter").ToString();
        var task = new Dictionary<string, object> { ["title"] = title, ["completed"] = false, ["id"] = taskId };
        db.StringSet($"task:{taskId}", JsonSerializer.Serialize(task));
        db.SetAdd("task_ids", taskId);
        return Results.Json(task, statusCode: 201);
    }
    return Results.Json(new { error = "Title required" }, statusCode: 400);
});

app.MapGet("/api/health", () =>
{
    try
    {
        db.Ping();
        return Results.Json(new { status = "running", redis = "healthy", container_type = "monolithic" });
    }
    catch
    {
        return Results.Json(new { status = "running", redis = "unhealthy", container_type = "monolithic" });
    }
});

string GetHtmlPage()
{
    var tasks = new List<Dictionary<string, object>>();
    var taskIds = db.SetMembers("task_ids");
    foreach (var taskId in taskIds)
    {
        var taskData = db.StringGet($"task:{taskId}");
        if (!taskData.IsNullOrEmpty)
        {
            var task = JsonSerializer.Deserialize<Dictionary<string, object>>(taskData!);
            if (task != null)
            {
                task["id"] = taskId.ToString();
                tasks.Add(task);
            }
        }
    }
    var totalTasks = tasks.Count;
    var completedTasks = tasks.Count(t => t.ContainsKey("completed") &&
        t["completed"] is JsonElement elem && elem.GetBoolean());

    var taskHtml = string.Join("\n", tasks.Select(t =>
    {
        var completed = t.ContainsKey("completed") && t["completed"] is JsonElement elem && elem.GetBoolean();
        var id = t["id"];
        var title = t.ContainsKey("title") && t["title"] is JsonElement titleElem ? titleElem.GetString() : "";
        return $@"
        <div class='task {(completed ? "completed" : "")}'>
            <strong>{title}</strong>
            <form action='/tasks/{id}/toggle' method='POST' style='display:inline;'>
                <button type='submit' class='complete-btn'>{(completed ? "Undo" : "Complete")}</button>
            </form>
            <form action='/tasks/{id}/delete' method='POST' style='display:inline;'>
                <button type='submit' class='delete-btn'>Delete</button>
            </form>
        </div>";
    }));

    return $@"
<!DOCTYPE html>
<html>
<head>
    <title>Task Manager</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }}
        .task {{ padding: 10px; margin: 10px 0; background: #f0f0f0; border-radius: 5px; }}
        .task.completed {{ background: #d4edda; text-decoration: line-through; }}
        form {{ margin: 20px 0; }}
        input[type='text'] {{ padding: 10px; width: 300px; }}
        button {{ padding: 10px 20px; background: #007bff; color: white; border: none; cursor: pointer; }}
        .delete-btn {{ background: #dc3545; margin-left: 10px; }}
        .complete-btn {{ background: #28a745; }}
        .stats {{ background: #e9ecef; padding: 15px; border-radius: 5px; margin: 20px 0; }}
    </style>
</head>
<body>
    <h1>Task Manager (.NET)</h1>
    <div class='stats'>
        <strong>Statistics:</strong> {totalTasks} total tasks | {completedTasks} completed | Server: Monolithic Container
    </div>
    <form action='/tasks' method='POST'>
        <input type='text' name='title' placeholder='Enter a new task...' required>
        <button type='submit'>Add Task</button>
    </form>
    <h2>Tasks</h2>
    {taskHtml}
    <hr>
    <h3>API Endpoints</h3>
    <ul>
        <li>GET /api/tasks - List all tasks</li>
        <li>POST /api/tasks - Create a task</li>
        <li>GET /api/health - Health check</li>
    </ul>
</body>
</html>";
}

app.Run("http://0.0.0.0:5000");
EOF
```

Create the project file:

```console
cat << 'EOF' > monolithic-dotnet/src/App.csproj
<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="StackExchange.Redis" Version="2.7.10" />
  </ItemGroup>
</Project>
EOF
```

### Step 3: Create the .NET Monolithic Dockerfile

```console
cat << 'EOF' > monolithic-dotnet/Dockerfile
# Monolithic Container - Anti-pattern demonstration
# This container runs multiple services: Redis + .NET Web App + Process Manager

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV DOTNET_CLI_TELEMETRY_OPTOUT=1

# Install ALL dependencies in a single layer (bad practice for demonstration)
RUN apt-get update && apt-get install -y \
    # .NET SDK for building
    wget \
    apt-transport-https \
    && wget https://packages.microsoft.com/config/ubuntu/22.04/packages-microsoft-prod.deb -O packages-microsoft-prod.deb \
    && dpkg -i packages-microsoft-prod.deb \
    && rm packages-microsoft-prod.deb \
    && apt-get update && apt-get install -y \
    dotnet-sdk-8.0 \
    # Redis server
    redis-server \
    # Process manager
    supervisor \
    # Debugging tools (often included unnecessarily)
    curl \
    vim \
    htop \
    net-tools \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and build the application
COPY src/ ./
RUN dotnet restore && dotnet publish -c Release -o /app/publish

# Create supervisord configuration
RUN mkdir -p /var/log/supervisor
COPY <<SUPERVISOR_CONF /etc/supervisor/conf.d/supervisord.conf
[supervisord]
nodaemon=true
logfile=/var/log/supervisor/supervisord.log
pidfile=/var/run/supervisord.pid

[program:redis]
command=/usr/bin/redis-server --protected-mode no
autostart=true
autorestart=true
stdout_logfile=/var/log/supervisor/redis-stdout.log
stderr_logfile=/var/log/supervisor/redis-stderr.log
priority=1

[program:webapp]
command=/app/publish/App
directory=/app/publish
autostart=true
autorestart=true
stdout_logfile=/var/log/supervisor/webapp-stdout.log
stderr_logfile=/var/log/supervisor/webapp-stderr.log
priority=2
environment=ASPNETCORE_URLS="http://0.0.0.0:5000"
SUPERVISOR_CONF

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
EOF
```

### Step 4: Build and Run the .NET Monolithic Container

```console
cd ~/monolithic-containers/monolithic-dotnet
docker build -t task-app:monolithic-dotnet .
```

**Why does this take even longer than Python?** The .NET SDK alone is ~700MB. Combined with Redis, supervisord, and debugging tools, expect an image of 1GB+.

Check the image size:

```console
docker images task-app:monolithic-dotnet
```

Run the container:

```console
docker run -d --name monolithic-dotnet -p 5001:5000 task-app:monolithic-dotnet
```

Test it:

```console
curl http://localhost:5001/api/health
```

---

## Observing the Problems with Monolithic Containers

Now let's examine the problems that monolithic containers create. These steps apply to whichever track you chose.

### Problem 1: Large Image Size

**Why this matters:** Large images mean:
- Slower CI/CD pipelines (more time uploading/downloading)
- Higher storage costs in registries
- Slower container startup (more to pull)
- Larger attack surface (more packages = more potential vulnerabilities)

Analyze the image layers:

```console
# For Python track:
docker history task-app:monolithic-python

# For .NET track:
docker history task-app:monolithic-dotnet
```

**What to look for:** Notice how the layer with all the `apt-get install` commands is extremely large. It includes:
- Development tools not needed at runtime (gcc, build-essential)
- Debugging utilities that shouldn't be in production (vim, htop)
- Multiple service binaries (redis-server, supervisord)

### Problem 2: Multiple Processes

**Why this matters:** Docker's health checks, logging, and lifecycle management assume one process per container. With multiple processes:
- If Redis crashes, Docker may think the container is healthy (supervisord is still running)
- `docker stop` sends SIGTERM to supervisord, which may not properly shut down child processes
- Resource limits apply to the container, not individual processes

Check the running processes inside the container:

```console
# For Python:
docker exec monolithic-python ps aux

# For .NET:
docker exec monolithic-dotnet ps aux
```

**What you'll see:**
- `supervisord` (process manager) - PID 1
- `redis-server` (database)
- `python3` or `dotnet` (web application)

**The problem:** If Redis crashes, Docker doesn't know. Only supervisord sees it and attempts a restart. Your health checks and orchestration tools are blind to internal failures.

### Problem 3: Complex Log Management

**Why this matters:** When debugging production issues, you need to quickly find relevant log entries. Mixed logs from multiple services make this difficult:
- Which service produced an error?
- What was the sequence of events across services?
- How do you filter to just the API logs?

View the logs:

```console
# For Python:
docker logs monolithic-python

# For .NET:
docker logs monolithic-dotnet
```

**What you'll see:** Supervisord's output, but NOT the actual application or Redis logs. Those are hidden inside the container.

To see individual service logs, you need to access the container:

```console
# For Python:
docker exec monolithic-python cat /var/log/supervisor/webapp-stdout.log
docker exec monolithic-python cat /var/log/supervisor/redis-stdout.log

# For .NET:
docker exec monolithic-dotnet cat /var/log/supervisor/webapp-stdout.log
docker exec monolithic-dotnet cat /var/log/supervisor/redis-stdout.log
```

**The problem:** Standard logging solutions (ELK, CloudWatch, Datadog) consume `docker logs` output. They won't see your actual application logs without custom configuration.

### Problem 4: Scaling Limitations

**Why this matters:** In production, different components have different scaling needs:
- API: Scale based on request volume (may need 10+ instances)
- Redis: Usually 1 instance (stateful, harder to scale)
- Background workers: Scale based on queue depth

With monolithic containers, you can only scale everything together.

Let's demonstrate this problem:

```console
# Create additional instances (using Python as example)
docker run -d --name monolithic-python-2 -p 5002:5000 task-app:monolithic-python
docker run -d --name monolithic-python-3 -p 5003:5000 task-app:monolithic-python
```

**What went wrong?** Each container has its own Redis instance. They don't share data:

```console
# Add a task via one container
curl -X POST -H "Content-Type: application/json" \
  -d '{"title":"Task from container 1"}' \
  http://localhost:5000/api/tasks

# Check if it exists in another container - it won't!
curl http://localhost:5002/api/tasks
```

**The result:** Three separate, isolated applications instead of three instances of one application.

Stop the extra containers:

```console
docker stop monolithic-python-2 monolithic-python-3 2>/dev/null
docker rm monolithic-python-2 monolithic-python-3 2>/dev/null
```

### Problem 5: Update Complexity

**Why this matters:** In a healthy CI/CD pipeline, you want:
- Fast builds (ideally under 5 minutes)
- Small changes (easier to review, test, rollback)
- Independent deployments (API team doesn't wait for database team)

With monolithic containers, a 1-line Python fix requires:
1. Rebuilding the entire image (Redis, supervisord, all tools)
2. Testing the entire stack (even unchanged components)
3. Deploying everything together

Stop the monolithic containers:

```console
docker stop monolithic-python monolithic-dotnet 2>/dev/null
```

---

## Refactoring to Multi-Container Architecture

Now let's refactor this application into separate, focused containers. We'll create versions for both Python and .NET.

### Step 6: Create the Multi-Container Directory Structure

```console
cd ~/monolithic-containers
mkdir -p multi-container-python/web
mkdir -p multi-container-dotnet/web
```

### Step 7: Create the Optimized Python Web Application

The key changes from monolithic:
- No Redis installation (it's a separate container)
- No supervisord (single process)
- Connects to Redis via network (environment variable)
- Minimal base image (python:3.11-slim, not ubuntu:22.04)

```console
cat << 'EOF' > multi-container-python/web/app.py
from flask import Flask, render_template_string, request, jsonify, redirect, url_for
import redis
import json
import os

app = Flask(__name__)

# Connect to Redis using environment variable (external service)
redis_host = os.environ.get('REDIS_HOST', 'redis')
redis_port = int(os.environ.get('REDIS_PORT', 6379))
redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)

# HTML Template
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
        .stats { background: #d4edda; padding: 15px; border-radius: 5px; margin: 20px 0; }
        .hostname { color: #666; font-size: 0.9em; }
    </style>
</head>
<body>
    <h1>Task Manager (Python)</h1>
    <div class="stats">
        <strong>Statistics:</strong> {{ total_tasks }} total tasks | {{ completed_tasks }} completed<br>
        <span class="hostname">Server: Multi-Container Architecture | Web Instance: {{ hostname }}</span>
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
</body>
</html>
"""

def get_tasks():
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
    return redis_client.incr('task_counter')

@app.route('/')
def index():
    tasks = get_tasks()
    hostname = os.environ.get('HOSTNAME', 'unknown')
    return render_template_string(HTML_TEMPLATE, tasks=tasks,
                                  total_tasks=len(tasks),
                                  completed_tasks=len([t for t in tasks if t.get('completed')]),
                                  hostname=hostname)

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
        'redis_host': redis_host,
        'container_type': 'multi-container',
        'hostname': os.environ.get('HOSTNAME', 'unknown')
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
EOF
```

### Step 8: Create Optimized Python Dockerfile

**Why these choices matter:**
- `python:3.11-slim`: ~150MB vs ~500MB for ubuntu + python + tools
- No debugging tools: Smaller attack surface, faster builds
- Non-root user: Security best practice
- Single CMD: No supervisord needed

```console
cat << 'EOF' > multi-container-python/web/Dockerfile
# Optimized Multi-Container Dockerfile
# Single responsibility: Web application only

FROM python:3.11-slim

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Install only required Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .

# Switch to non-root user
USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/health')" || exit 1

CMD ["python", "app.py"]
EOF

cat << 'EOF' > multi-container-python/web/requirements.txt
flask==3.0.0
redis==5.0.1
EOF
```

### Step 9: Create Python Docker Compose Configuration

**Why use Docker Compose?**
- Defines the entire application stack as code
- Handles networking automatically (containers can reach each other by service name)
- Manages startup dependencies
- Enables easy scaling

```console
cat << 'EOF' > multi-container-python/docker-compose.yml
services:
  # Redis service - official minimal image
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
    networks:
      - app-network

  # Web application service
  web:
    build: ./web
    restart: unless-stopped
    ports:
      - "5000:5000"
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
    depends_on:
      redis:
        condition: service_healthy
    networks:
      - app-network

networks:
  app-network:
    driver: bridge

volumes:
  redis-data:
EOF
```

**Understanding the configuration:**
- `redis:7-alpine`: Official Redis image, only ~30MB
- `depends_on.condition: service_healthy`: Web won't start until Redis healthcheck passes
- `networks`: Both services on same network, can reach each other by service name
- `volumes`: Redis data persists across container restarts

### Step 10: Create the Optimized .NET Web Application

```console
cat << 'EOF' > multi-container-dotnet/web/Program.cs
using System.Text.Json;
using StackExchange.Redis;

var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();

// Connect to Redis using environment variable (external service)
var redisHost = Environment.GetEnvironmentVariable("REDIS_HOST") ?? "redis";
var redisPort = Environment.GetEnvironmentVariable("REDIS_PORT") ?? "6379";
var redis = ConnectionMultiplexer.Connect($"{redisHost}:{redisPort}");
var db = redis.GetDatabase();

app.MapGet("/", () => Results.Content(GetHtmlPage(db), "text/html"));

app.MapPost("/tasks", async (HttpRequest request) =>
{
    var form = await request.ReadFormAsync();
    var title = form["title"].ToString();
    if (!string.IsNullOrEmpty(title))
    {
        var taskId = db.StringIncrement("task_counter").ToString();
        var task = new { title, completed = false };
        db.StringSet($"task:{taskId}", JsonSerializer.Serialize(task));
        db.SetAdd("task_ids", taskId);
    }
    return Results.Redirect("/");
});

app.MapPost("/tasks/{id}/toggle", (string id) =>
{
    var taskData = db.StringGet($"task:{id}");
    if (!taskData.IsNullOrEmpty)
    {
        var task = JsonSerializer.Deserialize<Dictionary<string, object>>(taskData!);
        if (task != null)
        {
            var completed = task.ContainsKey("completed") &&
                task["completed"] is JsonElement elem && elem.GetBoolean();
            task["completed"] = !completed;
            db.StringSet($"task:{id}", JsonSerializer.Serialize(task));
        }
    }
    return Results.Redirect("/");
});

app.MapPost("/tasks/{id}/delete", (string id) =>
{
    db.KeyDelete($"task:{id}");
    db.SetRemove("task_ids", id);
    return Results.Redirect("/");
});

app.MapGet("/api/tasks", () =>
{
    var tasks = GetTasks(db);
    return Results.Json(tasks);
});

app.MapPost("/api/tasks", async (HttpRequest request) =>
{
    var body = await JsonSerializer.DeserializeAsync<Dictionary<string, string>>(request.Body);
    if (body != null && body.TryGetValue("title", out var title) && !string.IsNullOrEmpty(title))
    {
        var taskId = db.StringIncrement("task_counter").ToString();
        var task = new Dictionary<string, object> { ["title"] = title, ["completed"] = false, ["id"] = taskId };
        db.StringSet($"task:{taskId}", JsonSerializer.Serialize(task));
        db.SetAdd("task_ids", taskId);
        return Results.Json(task, statusCode: 201);
    }
    return Results.Json(new { error = "Title required" }, statusCode: 400);
});

app.MapGet("/api/health", () =>
{
    try
    {
        db.Ping();
        return Results.Json(new {
            status = "running",
            redis = "healthy",
            redis_host = redisHost,
            container_type = "multi-container",
            hostname = Environment.GetEnvironmentVariable("HOSTNAME") ?? "unknown"
        });
    }
    catch
    {
        return Results.Json(new { status = "running", redis = "unhealthy" });
    }
});

static List<Dictionary<string, object>> GetTasks(IDatabase db)
{
    var tasks = new List<Dictionary<string, object>>();
    var taskIds = db.SetMembers("task_ids");
    foreach (var taskId in taskIds)
    {
        var taskData = db.StringGet($"task:{taskId}");
        if (!taskData.IsNullOrEmpty)
        {
            var task = JsonSerializer.Deserialize<Dictionary<string, object>>(taskData!);
            if (task != null)
            {
                task["id"] = taskId.ToString();
                tasks.Add(task);
            }
        }
    }
    return tasks;
}

static string GetHtmlPage(IDatabase db)
{
    var tasks = GetTasks(db);
    var totalTasks = tasks.Count;
    var completedTasks = tasks.Count(t => t.ContainsKey("completed") &&
        t["completed"] is JsonElement elem && elem.GetBoolean());
    var hostname = Environment.GetEnvironmentVariable("HOSTNAME") ?? "unknown";

    var taskHtml = string.Join("\n", tasks.Select(t =>
    {
        var completed = t.ContainsKey("completed") && t["completed"] is JsonElement elem && elem.GetBoolean();
        var id = t["id"];
        var title = t.ContainsKey("title") && t["title"] is JsonElement titleElem ? titleElem.GetString() : "";
        return $@"
        <div class='task {(completed ? "completed" : "")}'>
            <strong>{title}</strong>
            <form action='/tasks/{id}/toggle' method='POST' style='display:inline;'>
                <button type='submit' class='complete-btn'>{(completed ? "Undo" : "Complete")}</button>
            </form>
            <form action='/tasks/{id}/delete' method='POST' style='display:inline;'>
                <button type='submit' class='delete-btn'>Delete</button>
            </form>
        </div>";
    }));

    return $@"
<!DOCTYPE html>
<html>
<head>
    <title>Task Manager</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }}
        .task {{ padding: 10px; margin: 10px 0; background: #f0f0f0; border-radius: 5px; }}
        .task.completed {{ background: #d4edda; text-decoration: line-through; }}
        form {{ margin: 20px 0; }}
        input[type='text'] {{ padding: 10px; width: 300px; }}
        button {{ padding: 10px 20px; background: #007bff; color: white; border: none; cursor: pointer; }}
        .delete-btn {{ background: #dc3545; margin-left: 10px; }}
        .complete-btn {{ background: #28a745; }}
        .stats {{ background: #d4edda; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .hostname {{ color: #666; font-size: 0.9em; }}
    </style>
</head>
<body>
    <h1>Task Manager (.NET)</h1>
    <div class='stats'>
        <strong>Statistics:</strong> {totalTasks} total tasks | {completedTasks} completed<br>
        <span class='hostname'>Server: Multi-Container Architecture | Web Instance: {hostname}</span>
    </div>
    <form action='/tasks' method='POST'>
        <input type='text' name='title' placeholder='Enter a new task...' required>
        <button type='submit'>Add Task</button>
    </form>
    <h2>Tasks</h2>
    {taskHtml}
</body>
</html>";
}

app.Run("http://0.0.0.0:5000");
EOF
```

### Step 11: Create Optimized .NET Dockerfile

**Why multi-stage build?**
- Build stage has SDK (~700MB) for compiling
- Runtime stage has only ASP.NET runtime (~200MB)
- Final image doesn't include build tools

```console
cat << 'EOF' > multi-container-dotnet/web/App.csproj
<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="StackExchange.Redis" Version="2.7.10" />
  </ItemGroup>
</Project>
EOF

cat << 'EOF' > multi-container-dotnet/web/Dockerfile
# Multi-stage build for optimized .NET image
# Stage 1: Build
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY App.csproj .
RUN dotnet restore
COPY Program.cs .
RUN dotnet publish -c Release -o /app/publish

# Stage 2: Runtime (much smaller)
FROM mcr.microsoft.com/dotnet/aspnet:8.0
WORKDIR /app

# Create non-root user for security
RUN useradd --create-home appuser
USER appuser

COPY --from=build /app/publish .

EXPOSE 5000
ENV ASPNETCORE_URLS=http://0.0.0.0:5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

ENTRYPOINT ["dotnet", "App.dll"]
EOF
```

### Step 12: Create .NET Docker Compose Configuration

```console
cat << 'EOF' > multi-container-dotnet/docker-compose.yml
services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
    networks:
      - app-network

  web:
    build: ./web
    restart: unless-stopped
    ports:
      - "5001:5000"
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
    depends_on:
      redis:
        condition: service_healthy
    networks:
      - app-network

networks:
  app-network:
    driver: bridge

volumes:
  redis-data:
EOF
```

---

## Build and Run the Multi-Container Applications

### Step 13: Start the Multi-Container Applications

Start the Python multi-container application:

```console
cd ~/monolithic-containers/multi-container-python
docker compose up -d --build
```

Start the .NET multi-container application (if following that track):

```console
cd ~/monolithic-containers/multi-container-dotnet
docker compose up -d --build
```

Verify all services are running:

```console
docker compose ps
```

Test the applications:

```console
# Python (port 5000)
curl http://localhost:5000/api/health

# .NET (port 5001)
curl http://localhost:5001/api/health
```

---

## Comparing the Results

### Step 14: Compare Image Sizes

This is where the benefits become clear:

```console
echo "=== Image Size Comparison ==="
echo ""
echo "MONOLITHIC IMAGES:"
docker images task-app:monolithic-python --format "  Python: {{.Size}}" 2>/dev/null || echo "  Python: (not built)"
docker images task-app:monolithic-dotnet --format "  .NET:   {{.Size}}" 2>/dev/null || echo "  .NET: (not built)"
echo ""
echo "MULTI-CONTAINER IMAGES:"
docker images multi-container-python-web --format "  Python Web: {{.Size}}" 2>/dev/null || echo "  Python Web: (not built)"
docker images multi-container-dotnet-web --format "  .NET Web:   {{.Size}}" 2>/dev/null || echo "  .NET Web: (not built)"
docker images redis:7-alpine --format "  Redis:      {{.Size}}"
```

**Expected results:**

| Image | Monolithic Size | Multi-Container Size |
|-------|-----------------|---------------------|
| Python App | ~500-600 MB | ~150-180 MB |
| .NET App | ~1.0-1.2 GB | ~200-250 MB |
| Redis | (included) | ~30-40 MB |

**Why such a big difference?**
- Monolithic includes Ubuntu base + all tools + SDK + debugging utilities
- Multi-container uses minimal base images purpose-built for runtime
- .NET multi-stage build excludes the 700MB SDK from final image

### Step 15: Demonstrate Independent Scaling

**Why this matters:** In production, your API might need 10 instances during peak hours while Redis stays at 1. With multi-container, you scale what needs scaling.

```console
cd ~/monolithic-containers/multi-container-python
docker compose up -d --scale web=3 --no-recreate
```

Verify multiple web instances are running:

```console
docker compose ps
```

**Key observation:** All three web instances share the same Redis instance:

```console
# Add a task
curl -X POST -H "Content-Type: application/json" \
  -d '{"title":"Shared task from scaled environment"}' \
  http://localhost:5000/api/tasks

# All instances see the same data (refresh browser or curl multiple times)
curl http://localhost:5000/api/tasks
```

**Why this works:** The web containers connect to Redis by service name (`redis`). Docker's internal DNS routes all of them to the single Redis container.

Scale back down:

```console
docker compose up -d --scale web=1 --no-recreate
```

### Step 16: Compare Log Management

**Why clean logs matter:** When debugging production issues at 3 AM, you need to find the relevant error quickly. Mixed logs waste precious time.

With separate containers, logs are cleanly separated:

```console
cd ~/monolithic-containers/multi-container-python

# View only web application logs
docker compose logs web

# View only Redis logs
docker compose logs redis

# Follow logs from a specific service (Ctrl+C to stop)
docker compose logs -f web
```

**Compare to monolithic:**

```console
# Monolithic logs show only supervisord output
docker logs monolithic-python 2>/dev/null || echo "Monolithic container not running"
```

### Step 17: Demonstrate Independent Updates

**Why this matters:** In a microservices world, teams should be able to deploy their changes without coordinating with other teams.

```console
cd ~/monolithic-containers/multi-container-python

# Rebuild and restart only the web service
docker compose build web
docker compose up -d --no-deps web

# Redis continues running unaffected - data is preserved!
docker compose ps
curl http://localhost:5000/api/tasks
```

**The `--no-deps` flag** is crucial: it tells Compose to only restart the web service, not its dependencies.

---

## Benefits Summary

| Aspect | Monolithic | Multi-Container | Why It Matters |
|--------|------------|-----------------|----------------|
| **Image Size** | 500MB-1.2GB | ~200MB total | Faster deploys, lower costs |
| **Scaling** | All-or-nothing | Independent per service | Right-size resources |
| **Updates** | Rebuild entire image | Update only affected service | Faster CI/CD, less risk |
| **Logs** | Mixed, hard to parse | Separated by service | Faster debugging |
| **Failure Isolation** | One failure affects all | Services fail independently | Higher availability |
| **Resource Allocation** | Shared, uncontrolled | Configurable per service | Prevent resource starvation |
| **Security** | Larger attack surface | Minimal, focused images | Fewer vulnerabilities |
| **Team Independence** | Coupled workflow | Independent teams/deploys | Faster development |

---

## Cleanup

Stop and remove the multi-container applications:

```console
cd ~/monolithic-containers/multi-container-python
docker compose down -v

cd ~/monolithic-containers/multi-container-dotnet
docker compose down -v 2>/dev/null
```

Remove the monolithic containers and images:

```console
docker rm -f monolithic-python monolithic-dotnet 2>/dev/null
docker rmi task-app:monolithic-python task-app:monolithic-dotnet 2>/dev/null
```

Remove the multi-container images:

```console
docker rmi multi-container-python-web multi-container-dotnet-web 2>/dev/null
```

Clean up the lab directory (optional):

```console
cd ~
rm -rf ~/monolithic-containers
```

---

## Key Takeaways

1. **One process per container**: Each container should run a single process with a single responsibility. This improves isolation, scaling, and maintainability. **Why?** Docker's lifecycle management, health checks, and logging assume one process.

2. **Use official base images**: Leverage official, minimal images (like `redis:7-alpine` or `python:3.11-slim`) instead of building everything from scratch. **Why?** They're maintained, patched, and optimized by experts.

3. **Separate concerns**: Database, application, and other services should run in separate containers and communicate over the network. **Why?** Different scaling needs, update frequencies, and failure modes.

4. **Use Docker Compose**: Docker Compose simplifies orchestrating multi-container applications with networking, volumes, and dependencies. **Why?** Infrastructure as code means reproducible deployments.

5. **Enable independent scaling**: Multi-container architecture allows you to scale individual components based on their specific resource needs. **Why?** You pay for what you use, not what you bundle.

6. **Simplify updates and CI/CD**: Smaller, focused images are faster to build, test, and deploy. Changes to one service don't require rebuilding others. **Why?** Faster feedback loops, lower risk deployments.

7. **Improve observability**: Separate containers mean separate logs, metrics, and health checks for each service. **Why?** When things break, you need to find the problem fast.

---

## Congratulations

You have successfully demonstrated the challenges of monolithic containers and learned how to refactor them into a multi-container architecture using both Python and .NET examples. These principles apply to any technology stack - the patterns are universal.

This architecture is fundamental to building scalable, maintainable, and production-ready containerized applications.
