# Optimizing Container Images with Slim

## Overview

This lab demonstrates how to use Slim (SlimToolkit) to analyze and optimize Docker container images across multiple languages. Slim is a powerful tool that automatically identifies unused files and dependencies, reducing image sizes by 10-30x without modifying your Dockerfile.

By the end of this lab, you will:
- Understand how Slim analyzes container runtime behavior
- Optimize images for Python, Node.js, Go, and .NET applications
- Compare bloated vs. optimized images for each language
- Use Slim's xray command to understand image composition

## What is Slim?

Slim (formerly DockerSlim) is an open-source tool that optimizes container images by:

- Analyzing which files and dependencies are actually used at runtime
- Removing unnecessary files, packages, and layers
- Generating security profiles (Seccomp and AppArmor) automatically
- Reducing attack surface by eliminating unused components

Unlike multi-stage builds that require rewriting Dockerfiles, Slim works with existing images, making it ideal for optimizing legacy containers or images from third parties.

---

## Part 1: Setup and Python Application

### Step 1: Pull the Slim Docker Image

For this lab, we'll run Slim as a Docker container. Pull the patched Slim image:

```
docker pull aslaen/slim:patched
```

Verify the image was pulled:

```
docker images | grep slim
```

You should see the `aslaen/slim:patched` image in the list.

### Step 2: Create a Python Flask Application

Create a working directory for the entire lab:

```
mkdir -p ~/slim-lab/python && cd ~/slim-lab/python
```

Create a Flask application that represents a typical web service:

```
cat > app.py << 'EOF'
from flask import Flask, jsonify
import os
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route("/")
def hello():
    return jsonify({"message": "Hello from Flask!", "version": "1.0"})

@app.route("/health")
def health():
    return jsonify({"status": "healthy"})

@app.route("/api/info")
def info():
    return jsonify({
        "app": "flask-service",
        "python_version": os.popen("python --version").read().strip()
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
EOF
```

### Step 3: Create a Bloated Python Dockerfile

This Dockerfile represents common mistakes found in production images. Many teams install debugging tools during development and forget to remove them:

```
cat > Dockerfile << 'EOF'
FROM python:3.11

# Development and debugging tools that shouldn't be in production
RUN apt-get update && apt-get install -y \
    vim \
    curl \
    wget \
    git \
    htop \
    net-tools \
    iputils-ping \
    telnet \
    strace \
    dnsutils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app.py .

# Installing extra packages "just in case" they're needed
RUN pip install --no-cache-dir \
    flask \
    gunicorn \
    requests \
    redis \
    celery \
    sqlalchemy \
    psycopg2-binary

EXPOSE 5000
CMD ["python", "app.py"]
EOF
```

This image includes several common problems:
- Uses the full Python base image (over 1GB)
- Installs debugging tools (vim, htop, strace) not needed in production
- Includes networking tools (telnet, ping) that increase attack surface
- Installs Python packages the application never imports

### Step 4: Build and Analyze the Bloated Image

Build the bloated image:

```
docker build -t python-app:bloated .
```

Check the image size:

```
docker images python-app:bloated --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}"
```

The image should be around 1.1-1.3 GB. Use Slim's xray command to understand the image structure:

```
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aslaen/slim:patched xray python-app:bloated
```

The xray output shows each layer and its size, helping identify where the bloat comes from.

### Step 5: Optimize with Slim

Now use Slim to create an optimized image. Slim will start the container, monitor file access during HTTP probes, and build a minimal image containing only what was actually used:

```
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aslaen/slim:patched build --target python-app:bloated --tag python-app:slim --http-probe-cmd /health --http-probe-cmd /api/info
```

The `--http-probe-cmd` flags tell Slim which endpoints to probe. This exercises the application so Slim can detect all required files.

### Step 6: Compare Results

Compare the image sizes:

```
docker images | grep python-app
```

Expected results:

| Image | Size | Notes |
|-------|------|-------|
| python-app:bloated | ~1.8 GB | Full Python image with all packages |
| python-app:slim | ~78 MB | Only runtime dependencies |

That's approximately a 20x reduction in size.

### Step 7: Verify Functionality

Test that the optimized image works:

```
docker run -d --name test-python -p 5000:5000 python-app:slim
```

```
curl http://localhost:5000/
curl http://localhost:5000/health
curl http://localhost:5000/api/info
```

All endpoints should respond correctly. Clean up:

```
docker stop test-python && docker rm test-python
```

---

## Part 2: Node.js Application

### Step 8: Create a Node.js Express Application

Create a new directory for the Node.js example:

```
mkdir -p ~/slim-lab/nodejs && cd ~/slim-lab/nodejs
```

Create a package.json with typical dependencies:

```
cat > package.json << 'EOF'
{
  "name": "express-api",
  "version": "1.0.0",
  "main": "server.js",
  "scripts": {
    "start": "node server.js"
  },
  "dependencies": {
    "express": "^4.18.2"
  }
}
EOF
```

Create the Express server:

```
cat > server.js << 'EOF'
const express = require('express');
const app = express();
const PORT = 3000;

app.get('/', (req, res) => {
    res.json({ message: 'Hello from Express!', version: '1.0' });
});

app.get('/health', (req, res) => {
    res.json({ status: 'healthy' });
});

app.get('/api/time', (req, res) => {
    res.json({ timestamp: new Date().toISOString() });
});

app.listen(PORT, '0.0.0.0', () => {
    console.log(`Server running on port ${PORT}`);
});
EOF
```

### Step 9: Create a Bloated Node.js Dockerfile

This Dockerfile includes common Node.js bloat patterns:

```
cat > Dockerfile << 'EOF'
FROM node:20

# Installing build tools and debugging utilities
RUN apt-get update && apt-get install -y \
    python3 \
    make \
    g++ \
    vim \
    curl \
    wget \
    htop \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy everything including node_modules if present locally
COPY . .

# Install dependencies
RUN npm install

# Install global tools "for convenience"
RUN npm install -g nodemon pm2 typescript eslint

EXPOSE 3000
CMD ["npm", "start"]
EOF
```

Problems with this Dockerfile:
- Uses full Node.js image instead of slim or alpine
- Includes native build tools (python3, make, g++) for packages that don't need them
- Installs global packages (nodemon, typescript) not used in production
- Includes debugging tools

### Step 10: Build and Optimize the Node.js Image

Build the bloated image:

```
docker build -t node-app:bloated .
```

Check the size:

```
docker images node-app:bloated --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}"
```

The image should be around 1.2-1.4 GB. Now optimize with Slim:

```
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aslaen/slim:patched build --target node-app:bloated --tag node-app:slim --http-probe-cmd /health --http-probe-cmd /api/time
```

### Step 11: Compare and Verify Node.js Results

Compare sizes:

```
docker images | grep node-app
```

Expected results:

| Image | Size |
|-------|------|
| node-app:bloated | ~1.3 GB |
| node-app:slim | ~80-100 MB |

Test the optimized image:

```
docker run -d --name test-node -p 3000:3000 node-app:slim
```

```
curl http://localhost:3000/
curl http://localhost:3000/health
```

Clean up:

```
docker stop test-node && docker rm test-node
```

---

## Part 3: Go Application

Compiled languages like Go benefit from Slim differently. While multi-stage builds can produce small images, Slim can further reduce them by removing unused system libraries.

### Step 12: Create a Go Web Application

Create a new directory for the Go example:

```
mkdir -p ~/slim-lab/golang && cd ~/slim-lab/golang
```

Create a Go web server:

```
cat > main.go << 'EOF'
package main

import (
    "encoding/json"
    "log"
    "net/http"
    "runtime"
)

type Response struct {
    Message string `json:"message"`
    Version string `json:"version,omitempty"`
    Go      string `json:"go,omitempty"`
}

func main() {
    http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
        json.NewEncoder(w).Encode(Response{Message: "Hello from Go!"})
    })

    http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
        json.NewEncoder(w).Encode(Response{Message: "healthy"})
    })

    http.HandleFunc("/api/info", func(w http.ResponseWriter, r *http.Request) {
        json.NewEncoder(w).Encode(Response{
            Message: "Go API",
            Version: "1.0",
            Go:      runtime.Version(),
        })
    })

    log.Println("Server starting on port 8080")
    log.Fatal(http.ListenAndServe(":8080", nil))
}
EOF
```

Create the go.mod file:

```
cat > go.mod << 'EOF'
module example/api

go 1.22
EOF
```

### Step 13: Create a Bloated Go Dockerfile

This Dockerfile shows what happens when teams don't use multi-stage builds:

```
cat > Dockerfile << 'EOF'
FROM golang:1.22

# Installing unnecessary tools
RUN apt-get update && apt-get install -y \
    vim \
    curl \
    wget \
    htop \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

# Build with debug symbols (larger binary)
RUN go build -o server main.go

EXPOSE 8080
CMD ["./server"]
EOF
```

Problems:
- Uses full golang image with entire Go toolchain
- Includes debugging tools
- Leaves source code and Go cache in final image
- Binary includes debug symbols

### Step 14: Build and Optimize the Go Image

Build the bloated image:

```
docker build -t go-app:bloated .
```

Check the size:

```
docker images go-app:bloated --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}"
```

The image should be around 900 MB to 1 GB. Now optimize:

```
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aslaen/slim:patched build --target go-app:bloated --tag go-app:slim --http-probe-cmd /health --http-probe-cmd /api/info
```

### Step 15: Compare Go Results

Compare sizes:

```
docker images | grep go-app
```

Expected results:

| Image | Size |
|-------|------|
| go-app:bloated | ~950 MB |
| go-app:slim | ~10-15 MB |

This is a dramatic reduction because Go binaries are statically compiled, so Slim removes almost everything except the binary itself.

Test the optimized image:

```
docker run -d --name test-go -p 8080:8080 go-app:slim
```

```
curl http://localhost:8080/
curl http://localhost:8080/health
```

Clean up:

```
docker stop test-go && docker rm test-go
```

---

## Part 4: .NET Application

.NET applications often have large images due to the SDK and runtime dependencies. Slim can significantly reduce these while maintaining functionality.

### Step 16: Create a .NET Minimal API

Create a new directory for the .NET example:

```
mkdir -p ~/slim-lab/dotnet && cd ~/slim-lab/dotnet
```

Create the project file:

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

Create the minimal API:

```
cat > Program.cs << 'EOF'
var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();

app.MapGet("/", () => Results.Json(new { message = "Hello from .NET!", version = "1.0" }));
app.MapGet("/health", () => Results.Json(new { status = "healthy" }));
app.MapGet("/api/info", () => Results.Json(new {
    app = "dotnet-api",
    framework = System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription
}));

app.Run("http://0.0.0.0:5000");
EOF
```

### Step 17: Create a Bloated .NET Dockerfile

This Dockerfile represents common .NET image bloat:

```
cat > Dockerfile << 'EOF'
FROM mcr.microsoft.com/dotnet/sdk:8.0

# Development tools that shouldn't be in production
RUN apt-get update && apt-get install -y \
    vim \
    curl \
    wget \
    htop \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

# Restore and build
RUN dotnet restore
RUN dotnet publish -c Release -o out

WORKDIR /app/out
EXPOSE 5000
CMD ["dotnet", "api.dll"]
EOF
```

Problems with this Dockerfile:
- Uses full SDK image instead of runtime
- Includes source code and build artifacts
- Has debugging tools installed
- SDK contains compilers not needed at runtime

### Step 18: Build and Optimize the .NET Image

Build the bloated image:

```
docker build -t dotnet-app:bloated .
```

Check the size:

```
docker images dotnet-app:bloated --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}"
```

The image should be around 1-1.2 GB. Now optimize with Slim:

```
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aslaen/slim:patched build --target dotnet-app:bloated --tag dotnet-app:slim --http-probe-cmd /health --http-probe-cmd /api/info
```

### Step 19: Compare .NET Results

Compare the sizes:

```
docker images | grep dotnet-app
```

Expected results:

| Image | Size |
|-------|------|
| dotnet-app:bloated | ~1.1 GB |
| dotnet-app:slim | ~150-180 MB |

Test the optimized image:

```
docker run -d --name test-dotnet -p 5001:5000 dotnet-app:slim
```

```
curl http://localhost:5001/
curl http://localhost:5001/health
curl http://localhost:5001/api/info
```

Clean up:

```
docker stop test-dotnet && docker rm test-dotnet
```

---

## Part 5: Advanced Slim Features

### Step 20: Generate Security Profiles

Slim automatically generates Seccomp and AppArmor security profiles based on actual application behavior. Create an output directory and run Slim with artifact generation:

```
cd ~/slim-lab
mkdir -p slim-artifacts
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v ~/slim-lab/slim-artifacts:/output \
  aslaen/slim:patched build \
  --target python-app:bloated \
  --tag python-app:secure \
  --http-probe-cmd /health \
  --copy-meta-artifacts /output
```

Examine the generated artifacts:

```
ls -la ~/slim-lab/slim-artifacts/
```

Key artifacts include:
- **creport.json**: Detailed report of included files and their purposes
- **python-app-seccomp.json**: Security profile limiting system calls the container can make
- **python-app-apparmor-profile**: AppArmor profile for mandatory access control

### Step 21: Examine the Security Profiles

View the generated Seccomp profile to understand what system calls the application actually uses:

```
cat ~/slim-lab/slim-artifacts/python-app-seccomp.json | head -50
```

The Seccomp profile lists the specific system calls that were observed during the HTTP probe. In a production environment, you can use this profile to restrict your container to only these allowed system calls:

```
docker run -d --name secure-python \
  --security-opt seccomp=/home/ubuntu/slim-lab/slim-artifacts/python-app-seccomp.json \
  -p 5000:5000 \
  python-app:slim
```

Note: Seccomp profiles may need adjustment depending on your environment and kernel version. Test thoroughly before using in production.

View the AppArmor profile as well:

```
head -30 ~/slim-lab/slim-artifacts/python-app-apparmor-profile
```

These security profiles provide defense-in-depth by limiting what a container can do, even if an attacker gains code execution inside the container.

---

## Summary of Results

| Language | Bloated Size | Slim Size | Reduction |
|----------|--------------|-----------|-----------|
| Python Flask | ~1.8 GB | ~78 MB | 96% |
| Node.js Express | ~1.8 GB | ~153 MB | 92% |
| Go | ~1.4 GB | ~17 MB | 99% |
| .NET | ~1.3 GB | ~131 MB | 90% |

## When to Use Slim vs. Multi-Stage Builds

**Use Slim when:**
- Optimizing existing images without rewriting Dockerfiles
- Working with third-party or legacy images
- Needing to generate security profiles automatically
- You want to understand what files an image actually uses

**Use Multi-Stage Builds when:**
- Building new images from scratch
- You need reproducible builds in CI/CD
- You want fine-grained control over what's included
- Building compiled languages where you control the source

**Best Practice:** Combine both approaches. Use multi-stage builds for your base optimization, then apply Slim for further reduction and security profile generation.

## Cleanup

Remove all test images and directories:

```
docker rmi python-app:bloated python-app:slim python-app:secure 2>/dev/null
docker rmi node-app:bloated node-app:slim 2>/dev/null
docker rmi go-app:bloated go-app:slim 2>/dev/null
docker rmi dotnet-app:bloated dotnet-app:slim 2>/dev/null
rm -rf ~/slim-lab
```

## Key Takeaways

1. **Slim analyzes runtime behavior**, not just static dependencies, to identify what's truly needed
2. **Compiled languages** (Go, Rust) see the largest reductions because Slim removes the entire compiler toolchain
3. **Interpreted languages** (Python, Node.js, .NET) still see significant reductions from removing unused packages and system tools
4. **Security profiles** generated by Slim add defense-in-depth by limiting container capabilities
5. **No Dockerfile changes required**: Slim works with existing images, making it ideal for optimizing images you don't control
