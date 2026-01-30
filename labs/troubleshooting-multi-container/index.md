# Troubleshooting Multi-Container Applications

## Overview

In production environments, applications rarely run as a single container. Instead, they consist of multiple interconnected services: web servers, APIs, databases, caches, and more. When something goes wrong in these complex systems, the ability to quickly diagnose and fix issues becomes critical.

This lab teaches you a systematic approach to troubleshooting multi-container applications in both Docker Compose and Kubernetes environments. You'll also learn the trade-offs between running multiple containers in a single pod versus using separate pods for each service.

### What You Will Learn

- How to diagnose container crashes using logs and status information
- How to troubleshoot network connectivity between containers
- Key differences between multi-container pods and single-container pods in Kubernetes
- Why "one container per pod" is often the best practice
- Troubleshooting techniques for both Docker Compose and Kubernetes

### Prerequisites

- Basic familiarity with Docker commands
- Understanding of Docker Compose basics
- Basic knowledge of Kubernetes concepts (pods, deployments, services)

---

## Part 1: The Troubleshooting Methodology

Before diving into specific scenarios, let's establish a systematic approach to troubleshooting.

### Essential Commands

**Docker/Docker Compose:**

| Command | Purpose |
|---------|---------|
| `docker ps -a` | List all containers including stopped |
| `docker logs <container>` | View container logs |
| `docker compose logs -f` | Follow all service logs |
| `docker inspect <container>` | View full configuration |
| `docker network inspect` | Debug network connectivity |
| `docker exec -it <container> sh` | Interactive debugging |

**Kubernetes:**

| Command | Purpose |
|---------|---------|
| `kubectl get pods` | List pods and their status |
| `kubectl describe pod <name>` | Detailed pod information and events |
| `kubectl logs <pod>` | View pod logs (single container) |
| `kubectl logs <pod> -c <container>` | View specific container logs |
| `kubectl logs <pod> --all-containers` | View all container logs |
| `kubectl exec -it <pod> -- sh` | Interactive debugging |
| `kubectl get events --sort-by='.lastTimestamp'` | Recent cluster events |

---

## Part 2: Setup

### Start Minikube (Kubernetes)

```bash
minikube start --memory=5120
```

Verify it's running:

```bash
kubectl get nodes
```

### Create the Lab Directory

```bash
mkdir -p ~/troubleshooting-lab
cd ~/troubleshooting-lab
```

---

## Part 3: Docker Compose - Container Crash Diagnosis (Python + Redis)

This scenario demonstrates the most common container issue: missing configuration.

### Step 1: Create the Application Files

```bash
mkdir -p python-app
cat << 'EOF' > python-app/app.py
import os
import sys
from flask import Flask, jsonify

app = Flask(__name__)

REDIS_HOST = os.environ.get('REDIS_HOST')
if not REDIS_HOST:
    print("ERROR: REDIS_HOST environment variable is required", file=sys.stderr)
    sys.exit(1)

import redis
redis_client = redis.Redis(host=REDIS_HOST, decode_responses=True)

@app.route('/')
def home():
    return jsonify({"service": "Python Flask API", "status": "running"})

@app.route('/health')
def health():
    try:
        redis_client.ping()
        return jsonify({"status": "healthy", "redis": "connected"})
    except:
        return jsonify({"status": "unhealthy"}), 503

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
EOF

cat << 'EOF' > python-app/requirements.txt
flask==3.0.0
redis==5.0.1
EOF

cat << 'EOF' > python-app/Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
EXPOSE 5000
CMD ["python", "app.py"]
EOF
```

### Step 2: Create the Broken Docker Compose File

```bash
mkdir -p scenario-docker
cat << 'EOF' > scenario-docker/docker-compose.yml
services:
  api:
    build: ../python-app
    ports:
      - "5000:5000"
    # BUG: Missing REDIS_HOST environment variable

  redis:
    image: redis:7-alpine
EOF
```

### Step 3: Deploy and Observe the Problem

```bash
cd ~/troubleshooting-lab/scenario-docker
docker compose up -d --build
```

Check container status:

```bash
docker compose ps
```

You'll see the API container has `Exited (1)` status. **Why?** Exit code 1 indicates an application error.

### Step 4: Diagnose with Logs

```bash
docker logs scenario-docker-api-1
```

Output:
```
ERROR: REDIS_HOST environment variable is required
```

**The lesson:** Always check logs first. The error message tells us exactly what's wrong.

### Step 5: Apply the Fix

```bash
cat << 'EOF' > scenario-docker/docker-compose.yml
services:
  api:
    build: ../python-app
    ports:
      - "5000:5000"
    environment:
      - REDIS_HOST=redis   # Fixed: Added required env var

  redis:
    image: redis:7-alpine
EOF
```

Restart:

```bash
docker compose up -d
curl http://localhost:5000/health
```

### Step 6: Cleanup

```bash
docker compose down
cd ~/troubleshooting-lab
```

### Key Takeaways

1. **Exit code 1** = application error (check logs)
2. **Exit code 137** = OOM killed (check memory limits)
3. **Exit code 143** = graceful shutdown (SIGTERM)
4. Always check `docker logs` for crashed containers

---

## Part 4: Docker Compose - Network Connectivity Issues (Go + Redis)

This scenario demonstrates network isolation problems.

### Step 1: Create a Go Application

```bash
mkdir -p go-app
cat << 'EOF' > go-app/main.go
package main

import (
    "encoding/json"
    "fmt"
    "log"
    "net/http"
    "os"
    "time"
    "github.com/redis/go-redis/v9"
    "context"
)

var rdb *redis.Client
var ctx = context.Background()

func main() {
    redisHost := os.Getenv("REDIS_HOST")
    if redisHost == "" {
        redisHost = "redis"
    }

    rdb = redis.NewClient(&redis.Options{
        Addr: fmt.Sprintf("%s:6379", redisHost),
        DialTimeout: 5 * time.Second,
    })

    http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Content-Type", "application/json")
        if err := rdb.Ping(ctx).Err(); err != nil {
            w.WriteHeader(503)
            json.NewEncoder(w).Encode(map[string]string{"status": "unhealthy", "error": err.Error()})
            return
        }
        json.NewEncoder(w).Encode(map[string]string{"status": "healthy"})
    })

    log.Println("Starting server on :8080")
    log.Fatal(http.ListenAndServe(":8080", nil))
}
EOF

cat << 'EOF' > go-app/go.mod
module go-app
go 1.21
require github.com/redis/go-redis/v9 v9.3.0
EOF

cat << 'EOF' > go-app/Dockerfile
FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY go.mod .
RUN go mod download
COPY main.go .
RUN CGO_ENABLED=0 go build -o server .

FROM alpine:3.19
COPY --from=builder /app/server /server
CMD ["/server"]
EOF
```

### Step 2: Create Broken Docker Compose (Network Isolation)

```bash
mkdir -p scenario-network
cat << 'EOF' > scenario-network/docker-compose.yml
services:
  api:
    build: ../go-app
    ports:
      - "8080:8080"
    environment:
      - REDIS_HOST=redis
    networks:
      - frontend   # BUG: API is on frontend network

  redis:
    image: redis:7-alpine
    networks:
      - backend    # BUG: Redis is on backend network

networks:
  frontend:
  backend:
EOF
```

### Step 3: Deploy and Diagnose

```bash
cd ~/troubleshooting-lab/scenario-network
docker compose up -d --build
sleep 5
curl http://localhost:8080/health
```

You'll see: `{"status":"unhealthy","error":"dial tcp: lookup redis..."}`.

**Why?** Containers on different Docker networks cannot resolve each other's DNS names.

### Step 4: Investigate Networks

```bash
docker network ls | grep scenario
docker network inspect scenario-network_frontend
docker network inspect scenario-network_backend
```

### Step 5: Apply the Fix

```bash
cat << 'EOF' > scenario-network/docker-compose.yml
services:
  api:
    build: ../go-app
    ports:
      - "8080:8080"
    environment:
      - REDIS_HOST=redis
    networks:
      - app-network   # Fixed: Same network

  redis:
    image: redis:7-alpine
    networks:
      - app-network   # Fixed: Same network

networks:
  app-network:
EOF

docker compose down
docker compose up -d
curl http://localhost:8080/health
```

### Step 6: Cleanup

```bash
docker compose down
cd ~/troubleshooting-lab
```

---

## Part 5: Docker Compose - Startup Order Issues (.NET + SQL Server)

This scenario demonstrates a critical issue: **`depends_on` doesn't wait for service readiness**. This is especially problematic with databases that take time to initialize.

### Understanding the Problem

When you use `depends_on` in Docker Compose, it only waits for the container to **start**, not for the service inside to be **ready**. For SQL Server:
- Container starts in ~2 seconds
- SQL Server needs 15-30 seconds to initialize and accept connections

This race condition causes intermittent failures that are hard to debug.

### Step 1: Create the .NET Application

```bash
mkdir -p dotnet-app
cat << 'EOF' > dotnet-app/Program.cs
using Microsoft.Data.SqlClient;

var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();

var connectionString = Environment.GetEnvironmentVariable("CONNECTION_STRING")
    ?? "Server=db;Database=master;User Id=sa;Password=YourStrong@Passw0rd;TrustServerCertificate=true;";

// Try to connect at startup
Console.WriteLine("Attempting to connect to SQL Server...");
try
{
    using var connection = new SqlConnection(connectionString);
    connection.Open();
    Console.WriteLine("Successfully connected to SQL Server!");
}
catch (Exception ex)
{
    Console.WriteLine($"ERROR: Failed to connect to SQL Server: {ex.Message}");
    Environment.Exit(1);
}

app.MapGet("/", () => new { service = "DotNet API", status = "running" });

app.MapGet("/health", async () =>
{
    try
    {
        using var connection = new SqlConnection(connectionString);
        await connection.OpenAsync();
        return Results.Ok(new { status = "healthy", database = "connected" });
    }
    catch (Exception ex)
    {
        return Results.Json(new { status = "unhealthy", error = ex.Message }, statusCode: 503);
    }
});

app.MapGet("/users", async () =>
{
    try
    {
        using var connection = new SqlConnection(connectionString);
        await connection.OpenAsync();

        using var cmd = new SqlCommand(
            "IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Users') " +
            "CREATE TABLE Users (Id INT IDENTITY PRIMARY KEY, Name NVARCHAR(100))", connection);
        await cmd.ExecuteNonQueryAsync();

        using var insertCmd = new SqlCommand(
            "INSERT INTO Users (Name) VALUES (@Name); SELECT SCOPE_IDENTITY();", connection);
        insertCmd.Parameters.AddWithValue("@Name", $"User_{DateTime.Now.Ticks}");
        var newId = await insertCmd.ExecuteScalarAsync();

        using var countCmd = new SqlCommand("SELECT COUNT(*) FROM Users", connection);
        var count = await countCmd.ExecuteScalarAsync();

        return Results.Ok(new { id = newId, totalUsers = count });
    }
    catch (Exception ex)
    {
        return Results.Json(new { error = ex.Message }, statusCode: 503);
    }
});

Console.WriteLine("Starting .NET API on port 8080");
app.Run("http://0.0.0.0:8080");
EOF

cat << 'EOF' > dotnet-app/App.csproj
<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.Data.SqlClient" Version="5.1.2" />
  </ItemGroup>
</Project>
EOF

cat << 'EOF' > dotnet-app/Dockerfile
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY App.csproj .
RUN dotnet restore
COPY Program.cs .
RUN dotnet publish -c Release -o /app

FROM mcr.microsoft.com/dotnet/aspnet:8.0
WORKDIR /app
COPY --from=build /app .
EXPOSE 8080
ENTRYPOINT ["dotnet", "App.dll"]
EOF
```

### Step 2: Create the Broken Docker Compose (No Healthcheck)

```bash
mkdir -p scenario-dotnet
cat << 'EOF' > scenario-dotnet/docker-compose.yml
services:
  api:
    build: ../dotnet-app
    ports:
      - "8080:8080"
    environment:
      - CONNECTION_STRING=Server=db;Database=master;User Id=sa;Password=YourStrong@Passw0rd;TrustServerCertificate=true;
    depends_on:
      - db   # BUG: This only waits for container start, not SQL Server readiness

  db:
    image: mcr.microsoft.com/mssql/server:2022-latest
    environment:
      - ACCEPT_EULA=Y
      - MSSQL_SA_PASSWORD=YourStrong@Passw0rd
EOF
```

### Step 3: Deploy and Observe the Race Condition

```bash
cd ~/troubleshooting-lab/scenario-dotnet
docker compose up -d --build
```

Watch the logs:

```bash
docker compose logs -f api
```

You'll likely see:

```
ERROR: Failed to connect to SQL Server: A network-related or instance-specific error...
```

The API tried to connect before SQL Server was ready, even though we used `depends_on`.

### Step 4: Check Container Status

```bash
docker compose ps
```

You'll see the API container has exited:

```
NAME                    IMAGE                  STATUS
scenario-dotnet-api-1   scenario-dotnet-api    Exited (1)
scenario-dotnet-db-1    mssql/server:2022      Up
```

**Why did this happen?** `depends_on` ensures the database container **started**, but SQL Server needs 15-30 seconds to initialize before accepting connections.

### Step 5: Apply the Fix with Healthcheck

The solution is to add a healthcheck to SQL Server and make the API wait for it:

```bash
cat << 'EOF' > scenario-dotnet/docker-compose.yml
services:
  api:
    build: ../dotnet-app
    ports:
      - "8080:8080"
    environment:
      - CONNECTION_STRING=Server=db;Database=master;User Id=sa;Password=YourStrong@Passw0rd;TrustServerCertificate=true;
    depends_on:
      db:
        condition: service_healthy   # Fixed: Wait for healthcheck to pass

  db:
    image: mcr.microsoft.com/mssql/server:2022-latest
    environment:
      - ACCEPT_EULA=Y
      - MSSQL_SA_PASSWORD=YourStrong@Passw0rd
    healthcheck:
      test: /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "YourStrong@Passw0rd" -C -Q "SELECT 1" || exit 1
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s   # Give SQL Server time to initialize
EOF
```

**Understanding the healthcheck:**
- `test`: Runs a SQL query to verify the database accepts connections
- `start_period`: Grace period during initialization (critical for databases)
- `condition: service_healthy`: API won't start until healthcheck passes

### Step 6: Redeploy with the Fix

```bash
docker compose down
docker compose up -d
```

Watch the startup process:

```bash
docker compose ps
```

You'll see the database shows `(health: starting)`:

```
NAME                    STATUS
scenario-dotnet-db-1    Up (health: starting)
```

The API container won't appear until the database is healthy. After 30-40 seconds:

```bash
docker compose ps
```

```
NAME                    STATUS
scenario-dotnet-api-1   Up
scenario-dotnet-db-1    Up (healthy)
```

### Step 7: Verify the Application Works

```bash
curl http://localhost:8080/
curl http://localhost:8080/health
curl http://localhost:8080/users
```

### Step 8: Cleanup

```bash
docker compose down
cd ~/troubleshooting-lab
```

### Key Takeaways

1. **`depends_on` only waits for container start** - Not service readiness
2. **Databases need healthchecks** - They take time to initialize
3. **Use `condition: service_healthy`** - Makes depends_on wait for actual readiness
4. **`start_period` is crucial** - Prevents false failures during slow startups
5. **Intermittent failures often indicate race conditions** - If it "works sometimes," check startup order

---

## Part 6: Kubernetes - Multi-Container Pod Challenges

Now let's explore Kubernetes and understand why running multiple containers in a single pod can create troubleshooting challenges.

### Understanding Multi-Container Pods

In Kubernetes, a Pod can contain multiple containers that:
- Share the same network namespace (localhost communication)
- Share storage volumes
- Are scheduled together on the same node
- Start and stop together

**When to use multi-container pods:**
- Sidecar patterns (log shippers, proxies)
- Adapter patterns (data format conversion)
- Ambassador patterns (proxy to external services)

**Challenges:**
- Container startup order is not guaranteed
- One crashing container affects pod health
- Logs from multiple containers are interleaved
- Cannot scale containers independently

### Step 1: Create a Multi-Container Pod with Issues

```bash
mkdir -p ~/troubleshooting-lab/k8s-multi
cat << 'EOF' > ~/troubleshooting-lab/k8s-multi/broken-pod.yaml
apiVersion: v1
kind: Pod
metadata:
  name: multi-container-app
  labels:
    app: multi-container-demo
spec:
  containers:
  # API container - tries to connect to Redis immediately
  - name: api
    image: python:3.11-slim
    command: ["/bin/sh", "-c"]
    args:
    - |
      pip install flask redis > /dev/null 2>&1
      python -c "
      import redis, sys
      try:
          r = redis.Redis(host='localhost', socket_connect_timeout=2)
          r.ping()
          print('Connected to Redis')
      except Exception as e:
          print(f'ERROR: Cannot connect to Redis: {e}', file=sys.stderr)
          sys.exit(1)

      from flask import Flask, jsonify
      app = Flask(__name__)

      @app.route('/')
      def home():
          return jsonify({'status': 'running'})

      @app.route('/health')
      def health():
          try:
              r.ping()
              return jsonify({'status': 'healthy'})
          except:
              return jsonify({'status': 'unhealthy'}), 503

      app.run(host='0.0.0.0', port=5000)
      "
    ports:
    - containerPort: 5000

  # Redis container - starts at same time as API
  - name: redis
    image: redis:7-alpine
    ports:
    - containerPort: 6379

  # Noisy log generator - makes debugging harder
  - name: log-generator
    image: busybox
    command: ["/bin/sh", "-c", "while true; do echo \"[LOG] Processing batch $(shuf -i 1-1000 -n 1)\"; sleep 1; done"]
EOF
```

### Step 2: Deploy and Observe

```bash
kubectl apply -f ~/troubleshooting-lab/k8s-multi/broken-pod.yaml
```

Watch the pod status:

```bash
kubectl get pods -w
```

You might see the pod cycling through states or showing `CrashLoopBackOff`. **Why?** The API container might start before Redis is ready.

### Step 3: Troubleshoot with Kubernetes Commands

Check pod events:

```bash
kubectl describe pod multi-container-app
```

Look at the Events section at the bottom - this shows container start/restart history.

View logs from a specific container:

```bash
kubectl logs multi-container-app -c api
kubectl logs multi-container-app -c redis
kubectl logs multi-container-app -c log-generator
```

View all container logs together (notice how hard it is to read):

```bash
kubectl logs multi-container-app --all-containers=true
```

### Step 4: Understand the Problems

1. **Race condition:** API might start before Redis is listening
2. **Log complexity:** Three containers' logs are separate, making correlation difficult
3. **Blast radius:** If API crashes, the whole pod restarts (affecting Redis)

### Step 5: Fix with Init Container

```bash
cat << 'EOF' > ~/troubleshooting-lab/k8s-multi/fixed-pod.yaml
apiVersion: v1
kind: Pod
metadata:
  name: multi-container-app-fixed
spec:
  # Init container runs first and waits
  initContainers:
  - name: wait-for-redis
    image: busybox
    command: ["/bin/sh", "-c"]
    args:
    - |
      echo "Giving Redis time to start..."
      sleep 5
      echo "Proceeding"

  containers:
  - name: api
    image: python:3.11-slim
    command: ["/bin/sh", "-c"]
    args:
    - |
      pip install flask redis > /dev/null 2>&1
      python -c "
      import redis, time
      r = None
      for i in range(10):
          try:
              r = redis.Redis(host='localhost', socket_connect_timeout=2)
              r.ping()
              print('Connected to Redis')
              break
          except:
              print(f'Waiting for Redis... attempt {i+1}')
              time.sleep(2)

      from flask import Flask, jsonify
      app = Flask(__name__)

      @app.route('/health')
      def health():
          return jsonify({'status': 'healthy'})

      app.run(host='0.0.0.0', port=5000)
      "
    ports:
    - containerPort: 5000

  - name: redis
    image: redis:7-alpine
EOF

kubectl delete pod multi-container-app --ignore-not-found
kubectl apply -f ~/troubleshooting-lab/k8s-multi/fixed-pod.yaml
kubectl get pods -w
```

### Step 6: Cleanup

```bash
kubectl delete pod multi-container-app-fixed --ignore-not-found
```

---

## Part 7: Kubernetes - Single Container Per Pod (Best Practice)

Now let's see how the same application works better with one container per pod.

### Benefits of Single Container Per Pod

1. **Independent scaling:** Scale API without scaling Redis
2. **Isolated failures:** API crash doesn't affect Redis
3. **Clean logs:** Each pod has one log stream
4. **Simpler updates:** Update API without touching Redis
5. **Better resource management:** Set limits per service

### Step 1: Create the Deployment

```bash
mkdir -p ~/troubleshooting-lab/k8s-single
cat << 'EOF' > ~/troubleshooting-lab/k8s-single/deployment.yaml
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports:
        - containerPort: 6379
        readinessProbe:
          exec:
            command: ["redis-cli", "ping"]
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: redis
spec:
  selector:
    app: redis
  ports:
  - port: 6379
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: python:3.11-slim
        command: ["/bin/sh", "-c"]
        args:
        - |
          pip install flask redis > /dev/null 2>&1
          python -c "
          import redis, time, socket

          for i in range(30):
              try:
                  r = redis.Redis(host='redis', socket_connect_timeout=2)
                  r.ping()
                  print('Connected to Redis')
                  break
              except Exception as e:
                  print(f'Waiting for Redis... {e}')
                  time.sleep(2)

          from flask import Flask, jsonify
          app = Flask(__name__)

          @app.route('/')
          def home():
              return jsonify({'pod': socket.gethostname()})

          @app.route('/health')
          def health():
              try:
                  r.ping()
                  return jsonify({'status': 'healthy'})
              except:
                  return jsonify({'status': 'unhealthy'}), 503

          @app.route('/counter')
          def counter():
              return jsonify({'count': r.incr('counter')})

          app.run(host='0.0.0.0', port=5000)
          "
        ports:
        - containerPort: 5000
        env:
        - name: REDIS_HOST
          value: "redis"
---
apiVersion: v1
kind: Service
metadata:
  name: api
spec:
  selector:
    app: api
  ports:
  - port: 80
    targetPort: 5000
  type: NodePort
EOF
```

### Step 2: Deploy

```bash
kubectl apply -f ~/troubleshooting-lab/k8s-single/deployment.yaml
kubectl get pods -w
```

Wait for all pods to be Running.

### Step 3: Test the Application

```bash
# Get the NodePort
kubectl get svc api

# Test via minikube
minikube service api --url
```

Use the URL to test:

```bash
API_URL=$(minikube service api --url)
curl $API_URL/
curl $API_URL/health
curl $API_URL/counter
```

### Step 4: Demonstrate Independent Scaling

```bash
# Scale API independently of Redis
kubectl scale deployment api --replicas=3
kubectl get pods -l app=api

# Watch requests go to different pods
for i in {1..5}; do curl -s $API_URL/ | jq -r '.pod'; done
```

### Step 5: Demonstrate Isolated Failures

```bash
# Delete one API pod - others keep serving
kubectl delete pod -l app=api --field-selector=status.phase=Running --wait=false
kubectl get pods -l app=api

# Application still works
curl $API_URL/health
```

### Step 6: Clean Troubleshooting with Single Container Pods

View logs for specific service:

```bash
# API logs only
kubectl logs -l app=api --all-containers

# Redis logs only
kubectl logs -l app=redis
```

Compare to multi-container pod where logs are mixed together.

### Step 7: Troubleshoot Service Discovery Issues

Let's create a broken version to practice troubleshooting:

```bash
cat << 'EOF' > ~/troubleshooting-lab/k8s-single/broken.yaml
---
apiVersion: v1
kind: Service
metadata:
  name: redis-db   # Note: Different service name
spec:
  selector:
    app: redis
  ports:
  - port: 6379
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-broken
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api-broken
  template:
    metadata:
      labels:
        app: api-broken
    spec:
      containers:
      - name: api
        image: python:3.11-slim
        command: ["/bin/sh", "-c"]
        args:
        - |
          pip install redis > /dev/null 2>&1
          python -c "
          import redis
          # BUG: Wrong hostname - should be 'redis-db' not 'redis'
          r = redis.Redis(host='redis', socket_connect_timeout=5)
          r.ping()
          print('Connected')
          "
EOF

kubectl apply -f ~/troubleshooting-lab/k8s-single/broken.yaml
kubectl get pods -l app=api-broken -w
```

The pod will be in `CrashLoopBackOff`. Troubleshoot:

```bash
# Check logs
kubectl logs -l app=api-broken

# Check what services exist
kubectl get svc

# The fix: Use correct service name 'redis-db' or rename service to 'redis'
```

### Step 8: Cleanup

```bash
kubectl delete -f ~/troubleshooting-lab/k8s-single/deployment.yaml
kubectl delete -f ~/troubleshooting-lab/k8s-single/broken.yaml --ignore-not-found
```

---

## Part 8: Comparison Summary

### Multi-Container Pod vs Single Container Pod

| Aspect | Multi-Container Pod | Single Container Per Pod |
|--------|--------------------|-----------------------|
| **Scaling** | All containers scale together | Scale each service independently |
| **Failure isolation** | One crash affects all | Isolated failures |
| **Logs** | Mixed, specify `-c container` | Clean, one stream per pod |
| **Updates** | Must restart entire pod | Update services independently |
| **Network** | Share localhost | Use Service DNS names |
| **Use case** | Sidecars, tightly coupled | Most microservices |

### When to Use Multi-Container Pods

- Log shipping sidecars (fluentd, filebeat)
- Service mesh proxies (Envoy, Istio)
- Adapters that transform data formats
- Containers that truly share fate

### When to Use Single Container Pods

- Microservices that scale independently
- Services with different lifecycle requirements
- Most production applications

---

## Troubleshooting Checklist

### Docker Compose

- [ ] `docker compose ps` - Check container status
- [ ] `docker compose logs <service>` - Read service logs
- [ ] `docker network ls` - Check network configuration
- [ ] `docker exec -it <container> sh` - Debug from inside

### Kubernetes

- [ ] `kubectl get pods` - Check pod status
- [ ] `kubectl describe pod <name>` - View events and details
- [ ] `kubectl logs <pod> -c <container>` - View specific container logs
- [ ] `kubectl get svc` - Verify services exist
- [ ] `kubectl get events` - Check cluster events
- [ ] `kubectl exec -it <pod> -- sh` - Debug from inside

### Common Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `Exited (1)` | Missing config/env var | Check logs, add configuration |
| `CrashLoopBackOff` | App crashes repeatedly | Check logs, fix app error |
| Connection refused | Wrong hostname/network | Verify service names, check network |
| `ImagePullBackOff` | Wrong image name/tag | Fix image reference |
| Pod pending | Insufficient resources | Check resource requests/limits |

---

## Cleanup

```bash
# Stop minikube
minikube stop

# Remove Docker resources
cd ~/troubleshooting-lab
for dir in scenario-*/; do
  (cd "$dir" && docker compose down 2>/dev/null)
done

# Optional: Remove lab directory
rm -rf ~/troubleshooting-lab
```

---

## Congratulations!

You've learned to troubleshoot multi-container applications in both Docker Compose and Kubernetes. Key takeaways:

1. **Logs are your best friend** - Always check logs first
2. **Network issues are common** - Verify service names and network configuration
3. **Single container per pod is usually better** - Enables independent scaling and cleaner debugging
4. **Multi-container pods have their place** - Use for sidecars and tightly coupled containers
5. **Use probes in Kubernetes** - Readiness and liveness probes prevent issues

These troubleshooting skills apply to any containerized application, regardless of the underlying technology.
