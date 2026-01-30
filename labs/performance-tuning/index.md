# Performance Tuning Containerized Applications

## Overview

Container performance depends on multiple factors beyond application code: network configuration, storage drivers, volume mounts, and runtime settings all impact throughput and latency. This lab provides hands-on experience tuning these infrastructure components to maximize container performance.

**Objectives:**
- Understand Docker networking modes and their performance characteristics
- Configure storage options for optimal I/O performance
- Implement volume mount strategies that minimize latency
- Apply runtime tuning for .NET, Python, and Go applications
- Implement structured logging for observability without performance impact
- Configure service discovery and DNS for container environments
- Optimize container startup time with proper health checks
- Deploy and tune applications in Kubernetes using minikube
- Measure and validate performance improvements

**Prerequisites:**
- Familiarity with Docker networking and volume concepts
- Basic understanding of application profiling
- Completion of the resource management labs (CPU and memory constraints)

---

## Part 1: Networking Performance

### Understanding Docker Network Modes

Docker provides several networking modes, each with different performance characteristics:

| Mode | Description | Performance | Use Case |
|------|-------------|-------------|----------|
| bridge | Default isolated network with NAT | Moderate overhead from NAT translation | General purpose, isolation required |
| host | Container shares host network stack | Lowest latency, no NAT overhead | High-performance services |
| none | No networking | N/A | Security-sensitive batch processing |
| macvlan | Container gets own MAC address on physical network | Near-native performance | Legacy applications requiring L2 access |

The bridge network introduces latency through:
1. Network address translation (NAT) for outbound traffic
2. Port mapping for inbound traffic
3. iptables rules for traffic routing
4. Virtual ethernet pair overhead

For latency-sensitive applications, host networking eliminates these layers.

### Step 1: Create Test Applications

Create a working directory:

```
mkdir -p ~/perf-lab && cd ~/perf-lab
```

Create a .NET web API for benchmarking:

```
mkdir -p dotnet && cd ~/perf-lab/dotnet
```

```
cat > api.csproj << 'EOF'
<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
</Project>
EOF
```

```
cat > Program.cs << 'EOF'
var builder = WebApplication.CreateBuilder(args);

builder.WebHost.ConfigureKestrel(options =>
{
    options.Limits.MaxConcurrentConnections = 10000;
    options.Limits.MaxRequestBodySize = 10 * 1024 * 1024;
    options.Limits.KeepAliveTimeout = TimeSpan.FromMinutes(2);
});

var app = builder.Build();

app.MapGet("/", () => "OK");
app.MapGet("/health", () => Results.Json(new { status = "healthy" }));
app.MapGet("/data", () => Results.Json(new {
    timestamp = DateTime.UtcNow,
    data = new string('x', 1000)
}));

app.Run("http://0.0.0.0:5000");
EOF
```

```
cat > Dockerfile << 'EOF'
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY api.csproj .
RUN dotnet restore
COPY Program.cs .
RUN dotnet publish -c Release -o /app

FROM mcr.microsoft.com/dotnet/aspnet:8.0
WORKDIR /app
COPY --from=build /app .
ENV DOTNET_gcServer=1
ENV DOTNET_GCHeapHardLimit=0x10000000
EXPOSE 5000
ENTRYPOINT ["dotnet", "api.dll"]
EOF
```

Build the .NET image:

```
docker build -t dotnet-perf:v1 .
```

Create a Go application:

```
mkdir -p ~/perf-lab/golang && cd ~/perf-lab/golang
```

```
cat > go.mod << 'EOF'
module example/perf

go 1.22
EOF
```

```
cat > main.go << 'EOF'
package main

import (
    "encoding/json"
    "net/http"
    "strings"
    "time"
)

func main() {
    http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
        w.Write([]byte("OK"))
    })

    http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
        json.NewEncoder(w).Encode(map[string]string{"status": "healthy"})
    })

    http.HandleFunc("/data", func(w http.ResponseWriter, r *http.Request) {
        json.NewEncoder(w).Encode(map[string]interface{}{
            "timestamp": time.Now().UTC(),
            "data":      strings.Repeat("x", 1000),
        })
    })

    http.ListenAndServe(":8080", nil)
}
EOF
```

```
cat > Dockerfile << 'EOF'
FROM golang:1.22-alpine AS build
WORKDIR /app
COPY go.mod .
COPY main.go .
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o server main.go

FROM scratch
COPY --from=build /app/server /server
EXPOSE 8080
ENTRYPOINT ["/server"]
EOF
```

Build the Go image:

```
docker build -t go-perf:v1 .
```

### Step 2: Benchmark Bridge Network Performance

Install the benchmarking tool:

```
sudo apt-get update && sudo apt-get install -y apache2-utils
```

Start the .NET application with bridge networking (default):

```
docker run -d --name dotnet-bridge -p 5000:5000 dotnet-perf:v1
```

Wait for the container to start, then run a benchmark:

```
sleep 5
ab -n 10000 -c 100 http://localhost:5000/
```

Record the following metrics from the output:
- Requests per second
- Time per request (mean)
- Transfer rate

Stop the container:

```
docker stop dotnet-bridge && docker rm dotnet-bridge
```

### Step 3: Benchmark Host Network Performance

Start the same application with host networking:

```
docker run -d --name dotnet-host --network host dotnet-perf:v1
```

Run the same benchmark:

```
sleep 5
ab -n 10000 -c 100 http://localhost:5000/
```

Compare the results with bridge networking. Host networking typically shows:
- 10-30% higher requests per second
- Lower latency variance
- Reduced CPU overhead

Stop the container:

```
docker stop dotnet-host && docker rm dotnet-host
```

### Step 4: Compare Go Application Performance

Run the same tests with the Go application:

```
docker run -d --name go-bridge -p 8080:8080 go-perf:v1
sleep 3
ab -n 10000 -c 100 http://localhost:8080/
docker stop go-bridge && docker rm go-bridge
```

```
docker run -d --name go-host --network host go-perf:v1
sleep 3
ab -n 10000 -c 100 http://localhost:8080/
docker stop go-host && docker rm go-host
```

Go's lightweight HTTP server combined with host networking typically achieves the highest throughput among common language runtimes.

### Step 5: DNS Resolution Performance

DNS lookups inside containers can add latency. By default, Docker containers use the host's DNS settings, but resolution still passes through Docker's embedded DNS server.

Test DNS resolution time inside a container:

```
docker run --rm alpine sh -c "time nslookup google.com"
```

For applications making frequent external DNS queries, consider:

1. Using `--dns` to specify faster DNS servers:

```
docker run --rm --dns 8.8.8.8 alpine sh -c "time nslookup google.com"
```

2. Adding static entries with `--add-host` for frequently accessed internal services:

```
docker run --rm --add-host=api.internal:192.168.1.100 alpine cat /etc/hosts
```

---

## Part 2: Storage Performance

### Understanding Storage Drivers

Docker's storage driver manages how image layers and container writable layers are stored. Different drivers have different performance profiles:

| Driver | Performance | Stability | Use Case |
|--------|-------------|-----------|----------|
| overlay2 | Good read, moderate write | Excellent | Default for most Linux distributions |
| devicemapper | Good with direct-lvm | Good | Enterprise environments with LVM |
| btrfs | Good with SSD | Moderate | Systems using btrfs filesystem |
| zfs | Excellent | Good | Systems using ZFS |

Check the current storage driver:

```
docker info | grep "Storage Driver"
```

### Step 6: Measure Container Filesystem Performance

Container writes go to a writable layer managed by the storage driver. This introduces overhead compared to writing directly to the host filesystem.

Create a test container that measures write performance:

```
docker run --rm alpine sh -c "
    dd if=/dev/zero of=/testfile bs=1M count=100 conv=fsync 2>&1
    rm /testfile
"
```

The `conv=fsync` flag ensures data is written to disk before returning, providing accurate write speed measurements.

Record the write speed for comparison with volume mounts.

### Step 7: Compare Volume Mount Performance

Volumes bypass the storage driver, providing direct access to the host filesystem. Create a volume and test write performance:

```
docker volume create perf-test
```

```
docker run --rm -v perf-test:/data alpine sh -c "
    dd if=/dev/zero of=/data/testfile bs=1M count=100 conv=fsync 2>&1
    rm /data/testfile
"
```

The volume mount should show significantly faster write speeds because:
- No copy-on-write overhead
- No storage driver layer
- Direct filesystem access

### Step 8: Bind Mount Performance

Bind mounts map a host directory directly into the container. They offer similar performance to volumes but with direct host path access:

```
mkdir -p ~/perf-lab/bindtest
```

```
docker run --rm -v ~/perf-lab/bindtest:/data alpine sh -c "
    dd if=/dev/zero of=/data/testfile bs=1M count=100 conv=fsync 2>&1
    rm /data/testfile
"
```

Performance is nearly identical to volumes, but bind mounts are preferred when:
- The host path must be at a specific location
- Multiple containers need to share the same host directory
- Configuration files need to be injected at runtime

### Step 9: tmpfs for High-Speed Temporary Storage

For temporary data that does not need persistence, tmpfs mounts use RAM instead of disk:

```
docker run --rm --tmpfs /data:size=200M alpine sh -c "
    dd if=/dev/zero of=/data/testfile bs=1M count=100 2>&1
    rm /data/testfile
"
```

Note: The `conv=fsync` flag is omitted because tmpfs does not sync to disk.

tmpfs is ideal for:
- Application caches
- Session storage
- Temporary file processing
- Build artifacts that are discarded after container exit

The trade-off is that data is lost when the container stops, and memory usage counts against the container's memory limit.

---

## Part 3: Application-Specific Tuning

### Step 10: .NET Performance Configuration

.NET applications benefit from specific environment variables and runtime settings.

Create an optimized .NET Dockerfile:

```
cd ~/perf-lab/dotnet
```

```
cat > Dockerfile.optimized << 'EOF'
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY api.csproj .
RUN dotnet restore
COPY Program.cs .
RUN dotnet publish -c Release -o /app

FROM mcr.microsoft.com/dotnet/aspnet:8.0

# Performance-tuned environment variables
ENV DOTNET_gcServer=1
ENV DOTNET_GCHeapHardLimit=0x20000000
ENV DOTNET_ThreadPool_UnfairSemaphoreSpinLimit=6
ENV DOTNET_System_Threading_ThreadPool_MinThreads=100
ENV COMPlus_EnableDiagnostics=0

WORKDIR /app
COPY --from=build /app .
EXPOSE 5000
ENTRYPOINT ["dotnet", "api.dll"]
EOF
```

**Environment variable explanations:**

| Variable | Purpose |
|----------|---------|
| `DOTNET_gcServer=1` | Enables server garbage collection, optimized for throughput over latency |
| `DOTNET_GCHeapHardLimit` | Sets maximum heap size, preventing unbounded growth |
| `DOTNET_ThreadPool_UnfairSemaphoreSpinLimit` | Increases spin count before thread pool threads block |
| `DOTNET_System_Threading_ThreadPool_MinThreads` | Pre-allocates thread pool threads, reducing spin-up latency |
| `COMPlus_EnableDiagnostics=0` | Disables diagnostic ports, reducing overhead |

Build and test:

```
docker build -t dotnet-perf:v2 -f Dockerfile.optimized .
docker run -d --name dotnet-tuned --network host dotnet-perf:v2
sleep 5
ab -n 10000 -c 100 http://localhost:5000/
docker stop dotnet-tuned && docker rm dotnet-tuned
```

### Step 11: Python Performance Configuration

Create a Python application with performance tuning:

```
mkdir -p ~/perf-lab/python && cd ~/perf-lab/python
```

```
cat > app.py << 'EOF'
from flask import Flask, jsonify
import datetime

app = Flask(__name__)

@app.route("/")
def index():
    return "OK"

@app.route("/health")
def health():
    return jsonify({"status": "healthy"})

@app.route("/data")
def data():
    return jsonify({
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "data": "x" * 1000
    })
EOF
```

```
cat > Dockerfile << 'EOF'
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONOPTIMIZE=2

WORKDIR /app
COPY app.py .

RUN pip install --no-cache-dir flask gunicorn

EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--threads", "2", "--worker-class", "gthread", "app:app"]
EOF
```

**Configuration explanations:**

| Setting | Purpose |
|---------|---------|
| `PYTHONDONTWRITEBYTECODE=1` | Prevents .pyc file creation, reducing disk I/O |
| `PYTHONUNBUFFERED=1` | Disables output buffering for real-time logging |
| `PYTHONOPTIMIZE=2` | Removes docstrings and assertions for smaller memory footprint |
| `--workers 4` | Multiple worker processes to utilize CPU cores |
| `--threads 2` | Threads per worker for I/O-bound workloads |
| `--worker-class gthread` | Threaded worker class for concurrent request handling |

Build and test:

```
docker build -t python-perf:v1 .
docker run -d --name python-tuned --network host python-perf:v1
sleep 5
ab -n 10000 -c 100 http://localhost:5000/
docker stop python-tuned && docker rm python-tuned
```

### Step 12: Go Runtime Tuning

Go applications have fewer tuning options because the runtime is compiled into the binary, but environment variables can still impact performance:

```
cd ~/perf-lab/golang
```

```
cat > Dockerfile.optimized << 'EOF'
FROM golang:1.22-alpine AS build
WORKDIR /app
COPY go.mod .
COPY main.go .
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o server main.go

FROM scratch
COPY --from=build /app/server /server

ENV GOMAXPROCS=0
ENV GOGC=100

EXPOSE 8080
ENTRYPOINT ["/server"]
EOF
```

**Environment variable explanations:**

| Variable | Purpose |
|----------|---------|
| `GOMAXPROCS=0` | Defaults to number of available CPUs (optimal for most cases) |
| `GOGC=100` | Garbage collection target percentage; lower values run GC more frequently |

Note: Setting `GOGC` higher (e.g., 200) reduces GC frequency but increases memory usage. Setting it lower (e.g., 50) reduces memory but increases CPU overhead.

Build and test:

```
docker build -t go-perf:v2 -f Dockerfile.optimized .
docker run -d --name go-tuned --network host go-perf:v2
sleep 3
ab -n 10000 -c 100 http://localhost:8080/
docker stop go-tuned && docker rm go-tuned
```

---

## Part 4: I/O Optimization

### Step 13: Measure Disk I/O Impact

Applications performing frequent disk I/O benefit from proper volume configuration. Create a .NET application that writes to disk:

```
cd ~/perf-lab/dotnet
```

```
cat > IoTest.cs << 'EOF'
using System.Diagnostics;

var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();

app.MapGet("/write", async () => {
    var sw = Stopwatch.StartNew();
    var data = new byte[1024 * 1024]; // 1MB
    new Random().NextBytes(data);

    await File.WriteAllBytesAsync("/data/test.bin", data);
    sw.Stop();

    return Results.Json(new {
        operation = "write",
        bytes = data.Length,
        milliseconds = sw.ElapsedMilliseconds
    });
});

app.MapGet("/read", async () => {
    var sw = Stopwatch.StartNew();
    var data = await File.ReadAllBytesAsync("/data/test.bin");
    sw.Stop();

    return Results.Json(new {
        operation = "read",
        bytes = data.Length,
        milliseconds = sw.ElapsedMilliseconds
    });
});

app.Run("http://0.0.0.0:5000");
EOF
```

```
cat > IoTest.csproj << 'EOF'
<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
</Project>
EOF
```

```
cat > Dockerfile.io << 'EOF'
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY IoTest.csproj .
RUN dotnet restore
COPY IoTest.cs Program.cs
RUN dotnet publish -c Release -o /app

FROM mcr.microsoft.com/dotnet/aspnet:8.0
WORKDIR /app
COPY --from=build /app .
RUN mkdir /data
EXPOSE 5000
ENTRYPOINT ["dotnet", "IoTest.dll"]
EOF
```

Build:

```
docker build -t dotnet-io:v1 -f Dockerfile.io .
```

### Step 14: Compare I/O Performance Across Storage Options

Test with container filesystem (slowest):

```
docker run -d --name io-container -p 5000:5000 dotnet-io:v1
sleep 3
curl http://localhost:5000/write
curl http://localhost:5000/read
docker stop io-container && docker rm io-container
```

Test with a named volume:

```
docker volume create io-test
docker run -d --name io-volume -p 5000:5000 -v io-test:/data dotnet-io:v1
sleep 3
curl http://localhost:5000/write
curl http://localhost:5000/read
docker stop io-volume && docker rm io-volume
```

Test with tmpfs (fastest for temporary data):

```
docker run -d --name io-tmpfs -p 5000:5000 --tmpfs /data:size=100M dotnet-io:v1
sleep 3
curl http://localhost:5000/write
curl http://localhost:5000/read
docker stop io-tmpfs && docker rm io-tmpfs
```

Compare the milliseconds reported by each configuration. Expected relative performance:

1. tmpfs: Fastest (RAM-based, no disk I/O)
2. Named volume: Fast (direct filesystem access)
3. Container filesystem: Slowest (storage driver overhead)

---

## Part 5: Resource Limits and Performance

### Step 15: CPU Pinning for Consistent Performance

For applications requiring consistent latency, CPU pinning prevents the scheduler from moving processes between cores, eliminating cache invalidation:

```
docker run -d --name pinned --cpuset-cpus="0,1" --network host dotnet-perf:v2
sleep 5
ab -n 10000 -c 100 http://localhost:5000/
docker stop pinned && docker rm pinned
```

Compare with unpinned:

```
docker run -d --name unpinned --cpus="2" --network host dotnet-perf:v2
sleep 5
ab -n 10000 -c 100 http://localhost:5000/
docker stop unpinned && docker rm unpinned
```

CPU pinning is beneficial when:
- Latency consistency is more important than throughput
- The application has CPU-local caches (e.g., per-core data structures)
- NUMA-aware applications need to stay on specific memory domains

### Step 16: Memory Configuration for .NET

.NET's garbage collector performs better with explicit memory limits. Create a test to demonstrate:

```
cd ~/perf-lab/dotnet
```

Run without memory limit (GC must guess available memory):

```
docker run -d --name dotnet-nolimit --network host dotnet-perf:v2
sleep 5
ab -n 10000 -c 100 http://localhost:5000/data
docker stats --no-stream dotnet-nolimit
docker stop dotnet-nolimit && docker rm dotnet-nolimit
```

Run with explicit memory limit (GC knows boundaries):

```
docker run -d --name dotnet-limited -m 512m --network host dotnet-perf:v2
sleep 5
ab -n 10000 -c 100 http://localhost:5000/data
docker stats --no-stream dotnet-limited
docker stop dotnet-limited && docker rm dotnet-limited
```

Modern .NET versions detect container memory limits and configure the GC accordingly. The explicit limit allows the GC to make better decisions about when to collect and how much memory to retain.

---

## Part 6: Connection Pooling and Keep-Alive

### Step 17: HTTP Keep-Alive Performance

HTTP keep-alive reuses TCP connections, eliminating the overhead of connection establishment for each request.

Test without keep-alive (new connection per request):

```
docker run -d --name dotnet-test --network host dotnet-perf:v2
sleep 5
ab -n 10000 -c 100 http://localhost:5000/
```

Test with keep-alive (connection reuse):

```
ab -n 10000 -c 100 -k http://localhost:5000/
docker stop dotnet-test && docker rm dotnet-test
```

The `-k` flag enables keep-alive. Compare:
- Requests per second (higher with keep-alive)
- Time per request (lower with keep-alive)

Keep-alive is especially impactful for:
- HTTPS connections (TLS handshake is expensive)
- High-frequency API calls
- Microservice communication

---

## Part 7: Logging Best Practices

### Understanding Container Logging

Container logging differs from traditional application logging because stdout/stderr become the primary log channels. Docker captures these streams and processes them through logging drivers.

**Logging driver performance comparison:**

| Driver | Performance | Persistence | Use Case |
|--------|-------------|-------------|----------|
| json-file | Good | Local disk | Development, debugging |
| local | Better | Local disk with rotation | Production single-host |
| journald | Good | systemd journal | Systems using systemd |
| syslog | Moderate | Remote syslog server | Centralized logging |
| fluentd | Moderate | Forwarding to Fluentd | Complex log aggregation |
| none | Best | No logging | Maximum performance |

### Step 18: Configure Logging Drivers

Check the default logging driver:

```
docker info | grep "Logging Driver"
```

Run a container with the default json-file driver:

```
docker run -d --name log-json --log-driver json-file \
  --log-opt max-size=10m --log-opt max-file=3 \
  alpine sh -c "while true; do echo 'Log message at $(date)'; sleep 1; done"
```

The `max-size` and `max-file` options prevent unbounded log growth, which can fill disks and degrade performance.

View the log file location:

```
docker inspect --format='{{.LogPath}}' log-json
```

Stop the container:

```
docker stop log-json && docker rm log-json
```

### Step 19: Implement Structured Logging

Structured logging (JSON format) enables efficient parsing and querying in log aggregation systems. Plain text logs require regex parsing, which is CPU-intensive at scale.

Create a .NET application with structured logging:

```
cd ~/perf-lab/dotnet
```

```
cat > LoggingApp.cs << 'EOF'
using System.Text.Json;

var builder = WebApplication.CreateBuilder(args);
builder.Logging.ClearProviders();
builder.Logging.AddJsonConsole(options =>
{
    options.JsonWriterOptions = new JsonWriterOptions
    {
        Indented = false
    };
});

var app = builder.Build();
var logger = app.Services.GetRequiredService<ILogger<Program>>();

app.MapGet("/", () => {
    logger.LogInformation("Request received for root endpoint");
    return "OK";
});

app.MapGet("/process", () => {
    logger.LogInformation("Processing started with {ItemCount} items", 100);
    logger.LogInformation("Processing completed in {Duration}ms", 42);
    return Results.Json(new { status = "processed" });
});

app.Run("http://0.0.0.0:5000");
EOF
```

```
cat > Logging.csproj << 'EOF'
<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
</Project>
EOF
```

```
cat > Dockerfile.logging << 'EOF'
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY Logging.csproj .
RUN dotnet restore
COPY LoggingApp.cs Program.cs
RUN dotnet publish -c Release -o /app

FROM mcr.microsoft.com/dotnet/aspnet:8.0
WORKDIR /app
COPY --from=build /app .
ENV Logging__Console__FormatterName=Json
EXPOSE 5000
ENTRYPOINT ["dotnet", "Logging.dll"]
EOF
```

Build and test:

```
docker build -t dotnet-logging:v1 -f Dockerfile.logging .
docker run -d --name logging-test -p 5000:5000 dotnet-logging:v1
sleep 3
curl http://localhost:5000/process
docker logs logging-test | head -5
docker stop logging-test && docker rm logging-test
```

The structured JSON logs are machine-parseable and include metadata like timestamps and log levels without additional processing.

### Step 20: Logging Performance Impact

Excessive logging degrades performance. Create a benchmark to demonstrate:

```
docker run -d --name log-verbose --network host \
  --log-driver json-file dotnet-perf:v2
sleep 5
ab -n 5000 -c 50 http://localhost:5000/
docker stop log-verbose && docker rm log-verbose
```

Compare with logging disabled:

```
docker run -d --name log-none --network host \
  --log-driver none dotnet-perf:v2
sleep 5
ab -n 5000 -c 50 http://localhost:5000/
docker stop log-none && docker rm log-none
```

In production, balance observability needs with performance:
- Log errors and warnings always
- Use sampling for high-volume debug logs
- Configure appropriate log levels per environment
- Use asynchronous logging when available

---

## Part 8: Service Discovery and DNS

### Understanding Container DNS

Docker provides an embedded DNS server for container name resolution within user-defined networks. Understanding DNS behavior is essential for microservice architectures where services discover each other by name.

### Step 21: Create a User-Defined Network

The default bridge network does not support automatic DNS resolution between containers. Create a user-defined network:

```
docker network create perf-network
```

Start two containers on this network:

```
docker run -d --name service-a --network perf-network alpine sleep 3600
docker run -d --name service-b --network perf-network alpine sleep 3600
```

Test DNS resolution:

```
docker exec service-a ping -c 3 service-b
```

Containers can resolve each other by name because Docker's embedded DNS server provides name resolution for containers on user-defined networks.

### Step 22: DNS Resolution Methods

Docker containers can resolve names using different methods. Test resolution with `getent`, which uses the same mechanism as applications:

```
docker exec service-a getent hosts service-b
```

You can also use the network-qualified name for explicit resolution:

```
docker exec service-a nslookup service-b.perf-network
```

Note: Alpine's busybox `nslookup` may show NXDOMAIN errors for short names due to search domain behavior. Applications using standard library calls (like `ping` or `getent`) resolve correctly because they use Docker's embedded DNS properly.

For applications making many inter-service calls, DNS resolution time accumulates. Strategies to reduce DNS overhead:

1. **Connection pooling**: Reuse connections instead of creating new ones per request
2. **DNS caching**: Use a local DNS cache (applications often cache DNS internally)
3. **Static service addresses**: For stable services, consider fixed IPs

### Step 23: Network Aliases for Service Discovery

Network aliases allow a container to be reachable by multiple names:

```
docker run -d --name service-c --network perf-network \
  --network-alias api --network-alias backend \
  alpine sleep 3600
```

Verify both aliases resolve:

```
docker exec service-a getent hosts api
docker exec service-a getent hosts backend
```

This enables:
- Blue/green deployments (switch alias between versions)
- Service abstraction (containers reference logical names)
- Load balancing preparation (multiple containers with same alias)

Clean up:

```
docker stop service-a service-b service-c && docker rm service-a service-b service-c
docker network rm perf-network
```

---

## Part 9: Container Startup Optimization

### Understanding Startup Performance

Container startup time impacts:
- Application availability during scaling events
- Deployment speed in CI/CD pipelines
- Recovery time after failures

Startup time consists of:
1. Image pull time (if not cached)
2. Container creation overhead
3. Application initialization

### Step 24: Measure Startup Time

Measure container startup to first response:

```
cd ~/perf-lab/dotnet
```

```
time (docker run -d --name startup-test -p 5000:5000 dotnet-perf:v1 && \
  until curl -s http://localhost:5000/ > /dev/null; do sleep 0.1; done)
docker stop startup-test && docker rm startup-test
```

Compare with the lightweight Go application:

```
cd ~/perf-lab/golang
time (docker run -d --name startup-go -p 8080:8080 go-perf:v1 && \
  until curl -s http://localhost:8080/ > /dev/null; do sleep 0.1; done)
docker stop startup-go && docker rm startup-go
```

Go's compiled binary and minimal runtime typically starts faster than .NET's managed runtime.

### Step 25: Implement Health Checks

Health checks inform Docker (and orchestrators) when a container is ready to receive traffic:

```
cd ~/perf-lab/dotnet
```

```
cat > Dockerfile.healthcheck << 'EOF'
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY api.csproj .
RUN dotnet restore
COPY Program.cs .
RUN dotnet publish -c Release -o /app

FROM mcr.microsoft.com/dotnet/aspnet:8.0
WORKDIR /app
COPY --from=build /app .

HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:5000/health || exit 1

EXPOSE 5000
ENTRYPOINT ["dotnet", "api.dll"]
EOF
```

**Health check parameters:**

| Parameter | Purpose |
|-----------|---------|
| `--interval` | Time between health checks |
| `--timeout` | Maximum time for health check to complete |
| `--start-period` | Grace period for container initialization |
| `--retries` | Consecutive failures before marking unhealthy |

Install curl in the image (required for the health check):

```
cat > Dockerfile.healthcheck << 'EOF'
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY api.csproj .
RUN dotnet restore
COPY Program.cs .
RUN dotnet publish -c Release -o /app

FROM mcr.microsoft.com/dotnet/aspnet:8.0
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /app .

HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:5000/health || exit 1

EXPOSE 5000
ENTRYPOINT ["dotnet", "api.dll"]
EOF
```

Build the image:

```
docker build -t dotnet-health:v1 -f Dockerfile.healthcheck .
```

Start the container and immediately monitor health status to observe the transition from `starting` to `healthy`:

```
docker run -d --name health-test -p 5000:5000 dotnet-health:v1 && \
for i in {1..15}; do
  status=$(docker inspect --format="{{.State.Health.Status}}" health-test)
  echo "Second $i: $status"
  sleep 1
done
```

You should see output like:
```
Second 1: starting
Second 2: starting
...
Second 7: healthy
Second 8: healthy
```

The container transitions from `starting` to `healthy` after the first successful health check (which runs after the 5-second interval).

Clean up:

```
docker stop health-test && docker rm health-test
```

### Step 26: Startup Dependencies

Applications often depend on external services (databases, caches). Implement proper dependency handling:

```
cat > WaitApp.cs << 'EOF'
var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();
var logger = app.Services.GetRequiredService<ILogger<Program>>();

var ready = false;

app.MapGet("/", () => ready ? Results.Ok("OK") : Results.StatusCode(503));
app.MapGet("/health", () => ready ? Results.Ok() : Results.StatusCode(503));
app.MapGet("/ready", () => ready ? Results.Ok() : Results.StatusCode(503));

// Simulate dependency check
_ = Task.Run(async () => {
    logger.LogInformation("Checking dependencies...");
    await Task.Delay(5000); // Simulate waiting for database
    ready = true;
    logger.LogInformation("Dependencies ready, accepting traffic");
});

app.Run("http://0.0.0.0:5000");
EOF
```

```
cat > Wait.csproj << 'EOF'
<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
</Project>
EOF
```

```
cat > Dockerfile.wait << 'EOF'
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY Wait.csproj .
RUN dotnet restore
COPY WaitApp.cs Program.cs
RUN dotnet publish -c Release -o /app

FROM mcr.microsoft.com/dotnet/aspnet:8.0
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /app .

HEALTHCHECK --interval=2s --timeout=2s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:5000/ready || exit 1

EXPOSE 5000
ENTRYPOINT ["dotnet", "Wait.dll"]
EOF
```

Build and test:

```
docker build -t dotnet-wait:v1 -f Dockerfile.wait .
docker run -d --name wait-test -p 5000:5000 dotnet-wait:v1
```

Monitor the startup:

```
for i in {1..20}; do
  status=$(docker inspect --format="{{.State.Health.Status}}" wait-test 2>/dev/null || echo "starting")
  response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/ 2>/dev/null || echo "000")
  echo "Second $i: Health=$status, HTTP=$response"
  sleep 1
done
```

The application returns 503 until dependencies are ready, then transitions to 200.

```
docker stop wait-test && docker rm wait-test
```

---

## Part 10: Kubernetes Performance with Minikube

### Setting Up Minikube

Kubernetes provides orchestration features that impact container performance: scheduling, networking, storage, and health management. Minikube provides a local Kubernetes environment for testing.

### Step 27: Start Minikube

Start minikube with sufficient resources:

```
minikube start --memory=5120
```

Verify the cluster is running:

```
kubectl get nodes
```

Load the local images into minikube. The `docker save` pipe method works reliably with BuildKit-built images:

```
docker save dotnet-perf:v2 | minikube image load -
docker save go-perf:v2 | minikube image load -
```

Verify the images are available in minikube:

```
minikube image list | grep -E "dotnet-perf|go-perf"
```

### Step 28: Deploy Applications to Kubernetes

Create a deployment for the .NET application:

```
mkdir -p ~/perf-lab/k8s && cd ~/perf-lab/k8s
```

```
cat > dotnet-deployment.yaml << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dotnet-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: dotnet-api
  template:
    metadata:
      labels:
        app: dotnet-api
    spec:
      containers:
      - name: api
        image: dotnet-perf:v2
        imagePullPolicy: Never
        ports:
        - containerPort: 5000
        resources:
          requests:
            memory: "128Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "1000m"
        readinessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 5
          periodSeconds: 5
        livenessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 10
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: dotnet-api
spec:
  selector:
    app: dotnet-api
  ports:
  - port: 80
    targetPort: 5000
  type: ClusterIP
EOF
```

**Resource configuration explained:**

| Field | Purpose |
|-------|---------|
| `requests.memory` | Minimum memory guaranteed to the container |
| `requests.cpu` | Minimum CPU shares (250m = 0.25 cores) |
| `limits.memory` | Maximum memory; exceeding triggers OOM kill |
| `limits.cpu` | Maximum CPU; exceeding causes throttling |
| `readinessProbe` | Determines if pod should receive traffic |
| `livenessProbe` | Determines if pod should be restarted |

Apply the deployment:

```
kubectl apply -f dotnet-deployment.yaml
```

Watch pods start:

```
kubectl get pods -w
```

Press `Ctrl+C` when pods show `Running` and `Ready 1/1`.

### Step 29: Kubernetes DNS and Service Discovery

Kubernetes provides DNS-based service discovery. Pods can reach services by name within the cluster:

```
kubectl run test-pod --image=alpine --restart=Never -- sleep 3600
kubectl wait --for=condition=Ready pod/test-pod
```

Test service discovery using `getent`, which resolves names the same way applications do:

```
kubectl exec test-pod -- getent hosts dotnet-api
```

The service `dotnet-api` resolves to a cluster IP. Kubernetes DNS automatically creates records for services.

Note: Alpine's busybox `nslookup` may fail due to search domain behavior. Use `getent hosts` or test connectivity directly, which is what matters for applications.

Test connectivity:

```
kubectl exec test-pod -- wget -qO- http://dotnet-api/health
```

### Step 30: Horizontal Pod Autoscaling

Kubernetes can automatically scale deployments based on resource utilization.

Enable the metrics server:

```
minikube addons enable metrics-server
```

Wait for the metrics server to become available (this typically takes 60-90 seconds):

```
echo "Waiting for metrics server to be ready..."
until kubectl top nodes 2>/dev/null; do
  echo "Metrics not ready yet, waiting..."
  sleep 10
done
```

Create a Horizontal Pod Autoscaler:

```
kubectl autoscale deployment dotnet-api --cpu-percent=50 --min=2 --max=5
```

View the autoscaler:

```
kubectl get hpa
```

Generate load to trigger scaling. Run multiple parallel wget processes to generate sufficient CPU load:

```
kubectl run load-gen --image=busybox --restart=Never -- /bin/sh -c \
  "for i in 1 2 3 4 5 6 7 8; do while true; do wget -q -O- http://dotnet-api/; done & done; wait"
```

This spawns 8 parallel wget loops, which should drive CPU above the 50% threshold.

Watch the autoscaler respond (this may take 1-2 minutes):

```
kubectl get hpa -w
```

Press `Ctrl+C` after observing the replica count increase.

Stop the load generator:

```
kubectl delete pod load-gen
```

### Step 31: Pod Affinity and Anti-Affinity

For performance-critical applications, control pod placement:

```
cat > go-deployment.yaml << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: go-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: go-api
  template:
    metadata:
      labels:
        app: go-api
    spec:
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchLabels:
                  app: go-api
              topologyKey: kubernetes.io/hostname
      containers:
      - name: api
        image: go-perf:v2
        imagePullPolicy: Never
        ports:
        - containerPort: 8080
        resources:
          requests:
            memory: "32Mi"
            cpu: "100m"
          limits:
            memory: "64Mi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: go-api
spec:
  selector:
    app: go-api
  ports:
  - port: 80
    targetPort: 8080
  type: ClusterIP
EOF
```

**Affinity configuration explained:**

`podAntiAffinity` with `preferredDuringSchedulingIgnoredDuringExecution` tells Kubernetes to prefer placing pods on different nodes. This improves:
- Fault tolerance (node failure doesn't take all replicas)
- Resource distribution (pods spread CPU/memory load)

Note: In minikube with a single node, anti-affinity preferences cannot be satisfied, but the configuration demonstrates the pattern for multi-node clusters.

Apply:

```
kubectl apply -f go-deployment.yaml
```

### Step 32: Resource Quotas and Limit Ranges

Prevent resource exhaustion with namespace-level controls:

```
cat > resource-limits.yaml << 'EOF'
apiVersion: v1
kind: LimitRange
metadata:
  name: default-limits
spec:
  limits:
  - default:
      memory: "256Mi"
      cpu: "500m"
    defaultRequest:
      memory: "64Mi"
      cpu: "100m"
    type: Container
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: compute-quota
spec:
  hard:
    requests.cpu: "2"
    requests.memory: "2Gi"
    limits.cpu: "4"
    limits.memory: "4Gi"
    pods: "10"
EOF
```

**Configuration explained:**

`LimitRange` sets default resource requests/limits for containers that don't specify them. This ensures:
- Pods always have resource requests (enables proper scheduling)
- Pods have limits (prevents runaway resource consumption)

`ResourceQuota` limits total resource consumption in a namespace:
- Prevents a single namespace from exhausting cluster resources
- Enforces organizational resource allocation policies

Apply:

```
kubectl apply -f resource-limits.yaml
```

View the quota:

```
kubectl describe resourcequota compute-quota
```

### Step 33: Benchmark Kubernetes Service

Expose the service for external access:

```
kubectl port-forward service/dotnet-api 5000:80 &
PF_PID=$!
sleep 3
```

Run a benchmark:

```
ab -n 5000 -c 50 http://localhost:5000/
```

The benchmark traffic is load-balanced across the pod replicas by the Kubernetes service.

Stop port forwarding:

```
kill $PF_PID
```

---

## Summary

### Performance Optimization Checklist

**Networking:**
- [ ] Use host networking for latency-sensitive services
- [ ] Configure DNS servers for faster resolution
- [ ] Add static host entries for frequently accessed internal services
- [ ] Enable HTTP keep-alive for connection reuse
- [ ] Use user-defined networks for DNS-based service discovery

**Storage:**
- [ ] Use named volumes for persistent data (bypass storage driver)
- [ ] Use tmpfs for temporary/cache data
- [ ] Avoid writing to container filesystem for performance-critical I/O

**Logging:**
- [ ] Use structured JSON logging for efficient parsing
- [ ] Configure log rotation with `max-size` and `max-file`
- [ ] Set appropriate log levels per environment
- [ ] Consider `--log-driver none` for maximum performance when logging not required

**Startup and Health:**
- [ ] Implement health checks with appropriate intervals and timeouts
- [ ] Use readiness probes to control traffic routing
- [ ] Configure start periods to allow initialization time
- [ ] Handle dependencies with proper startup sequencing

**Runtime Configuration:**

| Language | Key Settings |
|----------|-------------|
| .NET | Server GC, thread pool minimums, heap limits |
| Python | Gunicorn workers/threads, PYTHONOPTIMIZE |
| Go | GOMAXPROCS, GOGC for memory/CPU trade-off |

**Resource Management:**
- [ ] Set memory limits to help GC make informed decisions
- [ ] Use CPU pinning for latency-sensitive workloads
- [ ] Match thread pool sizes to CPU allocation

**Kubernetes:**
- [ ] Set resource requests and limits on all containers
- [ ] Configure readiness and liveness probes
- [ ] Use Horizontal Pod Autoscaler for dynamic scaling
- [ ] Apply LimitRanges for default container resources
- [ ] Use ResourceQuotas to prevent resource exhaustion
- [ ] Consider pod anti-affinity for fault tolerance

### Performance Metrics Reference

| Metric | Tool | Command |
|--------|------|---------|
| HTTP throughput | ab | `ab -n 10000 -c 100 URL` |
| Disk I/O | dd | `dd if=/dev/zero of=file bs=1M count=100 conv=fsync` |
| Network latency | ping | `ping -c 100 host` |
| Container resources | docker stats | `docker stats --no-stream container` |
| Kubernetes pods | kubectl top | `kubectl top pods` |
| Kubernetes nodes | kubectl top | `kubectl top nodes` |

---

## Cleanup

Delete the minikube cluster (removes all Kubernetes resources):

```
minikube delete
```

Remove Docker test artifacts:

```
docker volume rm perf-test io-test 2>/dev/null
docker rmi dotnet-perf:v1 dotnet-perf:v2 dotnet-io:v1 dotnet-logging:v1 dotnet-health:v1 dotnet-wait:v1 go-perf:v1 go-perf:v2 python-perf:v1 2>/dev/null
rm -rf ~/perf-lab
```
