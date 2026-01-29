# Multi-Stage Builds: Creating Production-Ready Container Images

## Overview

Every file included in a container image increases its size, attack surface, and pull time. Development tools, compilers, package managers, and build artifacts are necessary during the build process but serve no purpose at runtime. Multi-stage builds solve this problem by allowing you to use multiple `FROM` statements in a single Dockerfile, each starting a new build stage. You can selectively copy artifacts from one stage to another, leaving behind everything you don't need in the final image.

This lab demonstrates multi-stage builds across four common scenarios:

- **Go applications**: Compiled binaries that need no runtime
- **Python applications**: Interpreted code with compiled dependencies
- **Node.js frontend apps**: Build-time compilation to static assets
- **.NET applications**: Compiled assemblies requiring only the runtime

By the end of this lab, you will understand how to:

- Convert single-stage Dockerfiles to multi-stage builds
- Reduce image sizes by 90% or more
- Separate build-time dependencies from runtime requirements
- Use minimal base images like `scratch`, `distroless`, and Alpine
- Apply security best practices in your final images

---

## Setup

Create a working directory for this lab:

```console
mkdir -p ~/multi-stage-lab && cd ~/multi-stage-lab
```

---

# Part 1: Go Application

Go compiles to a single static binary with no external dependencies. This makes Go applications ideal candidates for minimal container images because the final image only needs the compiled binary.

## Step 1: Create the Go Application

Create a simple HTTP server that responds to health checks:

```console
mkdir -p go-app && cd go-app
```

Create the main application file:

```console
cat << 'EOF' > main.go
package main

import (
    "encoding/json"
    "log"
    "net/http"
    "os"
)

type HealthResponse struct {
    Status  string `json:"status"`
    Version string `json:"version"`
}

func main() {
    port := os.Getenv("PORT")
    if port == "" {
        port = "8080"
    }

    http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
        w.Write([]byte("Hello from Go! <3\n"))
    })

    http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Content-Type", "application/json")
        json.NewEncoder(w).Encode(HealthResponse{
            Status:  "OK",
            Version: "1.0.0",
        })
    })

    log.Printf("Server starting on port %s", port)
    log.Fatal(http.ListenAndServe(":"+port, nil))
}
EOF
```

Initialize the Go module:

```console
cat << 'EOF' > go.mod
module docker-gs-ping

go 1.22
EOF
```

## Step 2: Build with a Single-Stage Dockerfile

First, build the application using a traditional single-stage approach to establish a baseline:

```console
cat << 'EOF' > Dockerfile.single
FROM golang:1.22

WORKDIR /app
COPY go.mod ./
COPY main.go ./

RUN CGO_ENABLED=0 GOOS=linux go build -o /app/server

EXPOSE 8080
CMD ["/app/server"]
EOF
```

Build and check the image size:

```console
docker build -f Dockerfile.single -t go-app:single .
docker images go-app:single --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
```

The image is over 800MB because it includes the entire Go toolchain: the compiler, standard library source code, and development tools. None of these are needed to run your compiled binary.

## Step 3: Convert to Multi-Stage Build

Now create a multi-stage Dockerfile that separates the build environment from the runtime environment:

```console
cat << 'EOF' > Dockerfile.multistage
# Stage 1: Build
FROM golang:1.22-alpine AS builder

WORKDIR /app
COPY go.mod ./
COPY main.go ./

# Build a statically-linked binary
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /app/server

# Stage 2: Runtime
FROM alpine:3.19

# Add a non-root user for security
RUN adduser -D -u 1000 appuser

WORKDIR /app
COPY --from=builder /app/server .

# Run as non-root
USER appuser

EXPOSE 8080
CMD ["./server"]
EOF
```

Build the multi-stage version:

```console
docker build -f Dockerfile.multistage -t go-app:multistage .
```

Compare the sizes:

```console
docker images go-app --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
```

The multi-stage image should be around 15MB compared to over 800MB for the single-stage version. That is a **98% reduction** in image size.

## Step 4: Go Even Smaller with Scratch

For Go applications with static linking, you can use the `scratch` base image, which contains literally nothing. Your binary is the only file in the entire image:

```console
cat << 'EOF' > Dockerfile.scratch
# Stage 1: Build
FROM golang:1.22-alpine AS builder

WORKDIR /app
COPY go.mod ./
COPY main.go ./

# Build fully static binary
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /app/server

# Stage 2: Minimal runtime (scratch = empty image)
FROM scratch

COPY --from=builder /app/server /server

EXPOSE 8080
ENTRYPOINT ["/server"]
EOF
```

Build and compare:

```console
docker build -f Dockerfile.scratch -t go-app:scratch .
docker images go-app --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
```

The scratch-based image is only about 7MB, containing just your compiled binary. There is no shell, no package manager, no other utilities. This is the smallest possible image and has the smallest attack surface.

**Trade-off**: Scratch images have no shell, so you cannot exec into them for debugging. Alpine-based images provide a good balance between size and debuggability.

## Step 5: Verify the Applications Work

Test each version to confirm they all function correctly:

```console
docker run -d --name go-single -p 8081:8080 go-app:single
docker run -d --name go-multi -p 8082:8080 go-app:multistage
docker run -d --name go-scratch -p 8083:8080 go-app:scratch

sleep 2

echo "=== Single-stage ===" && curl -s http://localhost:8081/health
echo "=== Multi-stage ===" && curl -s http://localhost:8082/health
echo "=== Scratch ===" && curl -s http://localhost:8083/health

docker rm -f go-single go-multi go-scratch
```

All three images produce identical output because they run the same compiled binary. The only difference is what surrounds that binary in the image.


---

# Part 2: Python Application with Dependencies

Python applications present a different challenge. The code itself is interpreted, but many Python packages include C extensions that must be compiled. The build tools needed to compile these extensions are not needed at runtime.

## Step 6: Create the Python Application

Create a Flask API with dependencies that include compiled extensions:

```console
mkdir -p python-app && cd python-app
```

Create the application:

```console
cat << 'EOF' > app.py
from flask import Flask, jsonify
import hashlib
import os

app = Flask(__name__)

@app.route('/')
def hello():
    return "Hello from Python!\n"

@app.route('/health')
def health():
    return jsonify({
        "status": "OK",
        "version": "1.0.0",
        "python": "3.11"
    })

@app.route('/hash/<text>')
def hash_text(text):
    """Compute SHA-256 hash of input text"""
    result = hashlib.sha256(text.encode()).hexdigest()
    return jsonify({"input": text, "sha256": result})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
EOF
```

Create requirements with packages that need compilation:

```console
cat << 'EOF' > requirements.txt
flask==3.0.0
gunicorn==21.2.0
cryptography==41.0.0
EOF
```

The `cryptography` package requires a C compiler and development headers to build. These tools are large and present security risks if left in production images.

## Step 7: Build Single-Stage Python Image

First, build with a single-stage approach:

```console
cat << 'EOF' > Dockerfile.single
FROM python:3.11

WORKDIR /app

# Install build dependencies (needed for cryptography)
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
EOF
```

Build and check the size:

```console
docker build -f Dockerfile.single -t python-app:single .
docker images python-app:single --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
```

This image is over 1GB because it includes the full Python distribution, development headers, compiler toolchain, and all build artifacts.

## Step 8: Convert to Multi-Stage Build

Create a multi-stage build that compiles dependencies in one stage and copies only the installed packages to the runtime stage:

```console
cat << 'EOF' > Dockerfile.multistage
# Stage 1: Build dependencies
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build tools
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application
COPY app.py .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
EOF
```

Build and compare:

```console
docker build -f Dockerfile.multistage -t python-app:multistage .
docker images python-app --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
```

The multi-stage image is roughly 200MB compared to over 1GB for the single-stage version. The build tools (gcc, headers, pip cache) are not included in the final image.

## Step 9: Verify Python Applications

Test both versions:

```console
docker run -d --name py-single -p 5001:5000 python-app:single
docker run -d --name py-multi -p 5002:5000 python-app:multistage

sleep 3

echo "=== Single-stage ===" && curl -s http://localhost:5001/health
echo "=== Multi-stage ===" && curl -s http://localhost:5002/health
echo "=== Hash endpoint ===" && curl -s http://localhost:5002/hash/hello

docker rm -f py-single py-multi
```



---

# Part 3: Node.js Frontend Application

Frontend applications built with React, Vue, or Angular have a particularly dramatic multi-stage story. The build process requires Node.js, npm, and hundreds of megabytes of development dependencies. But the final output is just static HTML, CSS, and JavaScript files that can be served by any web server.

## Step 10: Create the React Application

Create a simple React application:

```console
mkdir -p react-app && cd react-app
```

Create the package.json:

```console
cat << 'EOF' > package.json
{
  "name": "react-demo",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {
    "esbuild": "^0.19.0"
  },
  "scripts": {
    "build": "esbuild src/index.jsx --bundle --minify --outfile=dist/bundle.js"
  }
}
EOF
```

Create the source files:

```console
mkdir -p src dist

cat << 'EOF' > src/index.jsx
import React from 'react';
import { createRoot } from 'react-dom/client';

function App() {
  const [count, setCount] = React.useState(0);

  return (
    <div style={{fontFamily: 'sans-serif', padding: '20px'}}>
      <h1>React Multi-Stage Demo</h1>
      <p>Count: {count}</p>
      <button onClick={() => setCount(count + 1)}>Increment</button>
      <p style={{color: '#666', marginTop: '20px'}}>
        This application was built in a Node.js container but is served by nginx.
      </p>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
EOF

cat << 'EOF' > dist/index.html
<!DOCTYPE html>
<html>
<head>
  <title>React Multi-Stage Demo</title>
</head>
<body>
  <div id="root"></div>
  <script src="bundle.js"></script>
</body>
</html>
EOF
```

## Step 11: Build Single-Stage Node Image

Build with a single-stage approach where Node.js is the final image:

```console
cat << 'EOF' > Dockerfile.single
FROM node:20

WORKDIR /app
COPY package.json ./
RUN npm install

COPY src/ ./src/
COPY dist/index.html ./dist/
RUN npm run build

# Serve using a simple Node server
RUN npm install -g serve
EXPOSE 3000
CMD ["serve", "-s", "dist", "-l", "3000"]
EOF
```

Build and check the size:

```console
docker build -f Dockerfile.single -t react-app:single .
docker images react-app:single --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
```

This image is over 1GB because it includes Node.js, npm, all development dependencies, and the serve package.

## Step 12: Convert to Multi-Stage Build

Create a multi-stage build where Node.js builds the application and nginx serves the static files:

```console
cat << 'EOF' > Dockerfile.multistage
# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json ./
RUN npm install

COPY src/ ./src/
COPY dist/index.html ./dist/
RUN npm run build

# Stage 2: Production
FROM nginx:alpine

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
EOF
```

Build and compare:

```console
docker build -f Dockerfile.multistage -t react-app:multistage .
docker images react-app --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
```

The multi-stage image is around 40MB compared to over 1GB for the single-stage version. That is a **96% reduction**. The final image contains only nginx and your compiled static assets.

## Step 13: Verify React Applications

Test both versions:

```console
docker run -d --name react-single -p 3001:3000 react-app:single
docker run -d --name react-multi -p 3002:80 react-app:multistage

sleep 2

echo "=== Single-stage ===" && curl -s http://localhost:3001/ | head -5
echo "=== Multi-stage ===" && curl -s http://localhost:3002/ | head -5

docker rm -f react-single react-multi
```



---

# Part 4: .NET Application

.NET applications require the SDK (Software Development Kit) to build but only need the runtime to execute. The SDK includes the compiler, NuGet package manager, and development tools that add significant size to the image. By using multi-stage builds, you can compile with the full SDK and run with the minimal runtime.

## Step 14: Create the .NET Application

Create a simple ASP.NET minimal API:

```console
mkdir -p dotnet-app && cd dotnet-app
```

Create the project file:

```console
cat << 'EOF' > dotnet-app.csproj
<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
</Project>
EOF
```

Create the application:

```console
cat << 'EOF' > Program.cs
var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();

app.MapGet("/", () => "Hello from .NET!\n");

app.MapGet("/health", () => new {
    status = "OK",
    version = "1.0.0",
    runtime = System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription
});

app.Run("http://0.0.0.0:8080");
EOF
```

## Step 15: Build Single-Stage .NET Image

Build with a single-stage approach using the full SDK:

```console
cat << 'EOF' > Dockerfile.single
FROM mcr.microsoft.com/dotnet/sdk:8.0

WORKDIR /app
COPY *.csproj ./
COPY *.cs ./

RUN dotnet publish -c Release -o /app/publish

EXPOSE 8080
WORKDIR /app/publish
CMD ["dotnet", "dotnet-app.dll"]
EOF
```

Build and check the size:

```console
docker build -f Dockerfile.single -t dotnet-app:single .
docker images dotnet-app:single --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
```

This image is over 900MB because it includes the entire .NET SDK with compilers, build tools, and development dependencies.

## Step 16: Convert to Multi-Stage Build

Create a multi-stage build that compiles with the SDK but runs with the minimal runtime:

```console
cat << 'EOF' > Dockerfile.multistage
# Stage 1: Build with SDK
FROM mcr.microsoft.com/dotnet/sdk:8.0-alpine AS builder

WORKDIR /app
COPY *.csproj ./
RUN dotnet restore

COPY *.cs ./
RUN dotnet publish -c Release -o /app/publish

# Stage 2: Run with runtime only
FROM mcr.microsoft.com/dotnet/aspnet:8.0-alpine

WORKDIR /app
COPY --from=builder /app/publish .

# Create non-root user
RUN adduser -D -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080
ENTRYPOINT ["dotnet", "dotnet-app.dll"]
EOF
```

Build and compare:

```console
docker build -f Dockerfile.multistage -t dotnet-app:multistage .
docker images dotnet-app --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
```

The multi-stage image is around 110MB compared to over 900MB for the single-stage version. The SDK, compilers, and build tools are not included in the final image.

## Step 17: Verify .NET Applications

Test both versions:

```console
docker run -d --name dotnet-single -p 8091:8080 dotnet-app:single
docker run -d --name dotnet-multi -p 8092:8080 dotnet-app:multistage

sleep 3

echo "=== Single-stage ===" && curl -s http://localhost:8091/health
echo "=== Multi-stage ===" && curl -s http://localhost:8092/health

docker rm -f dotnet-single dotnet-multi
```



---

# Part 5: Advanced Techniques

## Step 18: Using Build Arguments for Flexibility

Build arguments let you parameterize your multi-stage builds. This is useful for building different versions or configurations from the same Dockerfile:

```console
mkdir -p advanced && cd advanced

cat << 'EOF' > Dockerfile.buildargs
# Accept build-time arguments
ARG GO_VERSION=1.22
ARG ALPINE_VERSION=3.19

# Stage 1: Build with specified Go version
FROM golang:${GO_VERSION}-alpine AS builder

WORKDIR /app
RUN go mod init example/app && \
    echo 'package main' > main.go && \
    echo 'import ("fmt"; "runtime")' >> main.go && \
    echo 'func main() { fmt.Printf("Built with Go %s\n", runtime.Version()) }' >> main.go && \
    CGO_ENABLED=0 go build -o /app/server

# Stage 2: Runtime with specified Alpine version
FROM alpine:${ALPINE_VERSION}

COPY --from=builder /app/server /server
CMD ["/server"]
EOF
```

Build with different versions:

```console
docker build -f Dockerfile.buildargs -t app:go122 .
docker build -f Dockerfile.buildargs --build-arg GO_VERSION=1.21 -t app:go121 .

docker run --rm app:go122
docker run --rm app:go121
```

## Step 19: Optimizing Build Cache

The order of instructions in your Dockerfile affects build cache efficiency. Copy files that change frequently last. Create a simple Go app to demonstrate:

```console
cat << 'EOF' > go.mod
module example/cache-demo
go 1.22
EOF

cat << 'EOF' > main.go
package main
import "fmt"
func main() { fmt.Println("Cache demo app") }
EOF

cat << 'EOF' > Dockerfile.cache
FROM golang:1.22-alpine AS builder

WORKDIR /app

# Copy dependency files first (changes less frequently)
COPY go.mod ./
RUN go mod download || true

# Copy source code last (changes most frequently)
COPY *.go ./
RUN CGO_ENABLED=0 go build -o /app/server

FROM alpine:3.19
COPY --from=builder /app/server /server
CMD ["/server"]
EOF

docker build -f Dockerfile.cache -t app:cached . 2>&1 | tail -5
```

When you change only the source code, Docker reuses the cached dependency layer, making rebuilds faster.

## Step 20: Security Scan Comparison

Multi-stage builds improve security by reducing the attack surface. Compare vulnerability counts between images:

```console
echo "=== Comparing image sizes and layers ==="
echo ""
echo "Go application images:"
docker images go-app --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
echo ""
echo "Python application images:"
docker images python-app --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
echo ""
echo "React application images:"
docker images react-app --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
echo ""
echo ".NET application images:"
docker images dotnet-app --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
```

Fewer packages mean fewer potential vulnerabilities. The scratch-based Go image has zero packages to scan.

---

## Cleanup

Remove all images and directories created during this lab:

```console
cd ~
docker rmi go-app:single go-app:multistage go-app:scratch 2>/dev/null
docker rmi python-app:single python-app:multistage 2>/dev/null
docker rmi react-app:single react-app:multistage 2>/dev/null
docker rmi dotnet-app:single dotnet-app:multistage 2>/dev/null
docker rmi app:go122 app:go121 app:cached 2>/dev/null
rm -rf ~/multi-stage-lab
```

---

## Summary

Multi-stage builds provide significant benefits across all application types:

| Application | Single-Stage | Multi-Stage | Reduction |
|-------------|--------------|-------------|-----------|
| Go (Alpine) | ~850MB | ~15MB | 98% |
| Go (Scratch) | ~850MB | ~7MB | 99% |
| Python | ~1.1GB | ~200MB | 82% |
| React/Node | ~1.1GB | ~40MB | 96% |
| .NET | ~900MB | ~110MB | 88% |

**Key principles:**

1. **Separate build and runtime**: Use one stage for building, another for running
2. **Copy only what you need**: Use `COPY --from=builder` to selectively copy artifacts
3. **Choose minimal base images**: Alpine, slim, distroless, or scratch for runtime
4. **Order for cache efficiency**: Put frequently changing files last in the Dockerfile
5. **Run as non-root**: Add a non-root user in your final stage for security

**When to use which base image:**

| Base Image | Size | Use Case |
|------------|------|----------|
| `scratch` | 0 bytes | Statically linked binaries (Go, Rust) |
| `distroless` | ~20MB | Applications needing minimal runtime (SSL certs, timezone data) |
| `alpine` | ~7MB | When you need a shell for debugging |
| Language-slim | ~100-200MB | Python/Node applications needing the interpreter |

---

## Congratulations

You have learned how to apply multi-stage builds across Go, Python, Node.js, and .NET applications. These techniques reduce image size, improve security, speed up deployments, and lower storage costs. Multi-stage builds are a fundamental practice for production container images.
