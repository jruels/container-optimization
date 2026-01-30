# Analyzing and Securing Container Images

## Overview

Container images often contain far more than the application code developers intend to deploy. A typical production image may include debugging tools left over from development, package manager caches that serve no runtime purpose, and outdated libraries with known security vulnerabilities. Without proper analysis tools, these issues remain hidden until they cause problems in production.

This lab introduces three essential tools for container image analysis:

- **Dive**: Examines the internal layer structure of images to identify wasted space and inefficient build patterns
- **Trivy**: Scans images for known security vulnerabilities in operating system packages and application dependencies
- **Hadolint**: Validates Dockerfiles against established best practices before images are built

By the end of this lab, participants will understand how to identify and remediate common image problems across Python, Go, and .NET applications.

---

## Part 1: Understanding the Tools

### Why Image Analysis Matters

Container images are composed of read-only layers. Each instruction in a Dockerfile (RUN, COPY, ADD) creates a new layer that gets stacked on top of previous layers. This layered architecture has important implications:

**Layer persistence**: When a file is deleted in a later layer, it still exists in the earlier layer and contributes to image size. For example, if you install build tools in one layer and attempt to remove them in the next layer, the image size does not decrease.

**Vulnerability inheritance**: Base images contain operating system packages that may have known vulnerabilities. Your application inherits these vulnerabilities even if it never uses the affected packages.

**Attack surface**: Every package, library, and tool in an image is a potential entry point for attackers. Minimizing image contents reduces the attack surface.

### Tool Overview

**Dive** addresses the visibility problem. Docker images are opaque by default. The `docker history` command shows layer sizes but not contents. Dive provides an interactive interface to explore exactly what files each layer contains, making it possible to identify unnecessary files and understand why an image is larger than expected.

**Trivy** addresses the security problem. It maintains an updated database of known vulnerabilities (CVEs) and compares the packages in your image against this database. Trivy scans both operating system packages (apt, apk, yum) and application dependencies (pip, npm, NuGet, Go modules).

**Hadolint** addresses the prevention problem. Rather than finding issues after an image is built, Hadolint analyzes Dockerfiles to catch problematic patterns before they become embedded in images. It enforces best practices that lead to smaller, more secure, and more maintainable images.

---

## Part 2: Environment Setup

### Step 1: Install Dive

Dive is distributed as a Debian package. The following commands download and install version 0.13.1:

```
wget https://github.com/wagoodman/dive/releases/download/v0.13.1/dive_0.13.1_linux_amd64.deb
sudo dpkg -i dive_0.13.1_linux_amd64.deb
```

The installation places the `dive` binary in `/usr/local/bin`. Verify the installation succeeded:

```
dive --version
```

Expected output: `dive 0.13.1`

### Step 2: Verify Trivy Access

Trivy is distributed as a Docker image, eliminating the need for local installation. The scanner runs inside a container and accesses the Docker daemon through a socket mount. Verify that the Trivy image is accessible:

```
docker run --rm aquasec/trivy --version
```

This command pulls the Trivy image if not already present and displays the version number. The `--rm` flag ensures the container is removed after execution.

### Step 3: Create Working Directory

All lab files will be created in a dedicated directory:

```
mkdir -p ~/tools-lab && cd ~/tools-lab
```

---

## Part 3: Create Sample Applications

This section creates three applications using intentionally suboptimal Dockerfiles. These represent common patterns found in real-world codebases and serve as examples for analysis.

### Step 4: Create Python Application

Create a directory for the Python application:

```
mkdir -p ~/tools-lab/python && cd ~/tools-lab/python
```

Create a minimal Flask web application. Flask is a lightweight web framework that handles HTTP routing and request/response processing:

```
cat > app.py << 'EOF'
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def index():
    return jsonify({"service": "python-api", "version": "1.0"})

@app.route("/health")
def health():
    return jsonify({"status": "healthy"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
EOF
```

Create a Dockerfile that demonstrates several common anti-patterns. Each issue is intentional and will be identified during analysis:

```
cat > Dockerfile << 'EOF'
FROM python:3.11

RUN apt-get update
RUN apt-get install -y vim curl wget
RUN apt-get install -y netcat-openbsd

WORKDIR /app
COPY app.py .

RUN pip install flask
RUN pip install requests
RUN pip install gunicorn

EXPOSE 5000
CMD ["python", "app.py"]
EOF
```

**Anti-patterns in this Dockerfile:**

1. **Multiple RUN commands**: Each RUN instruction creates a new layer. Separating apt-get update from apt-get install allows the package list to become stale if cached. Separating each pip install creates unnecessary layers.

2. **Unnecessary packages**: vim, curl, wget, and netcat are development and debugging tools. They add size and attack surface without providing runtime value.

3. **No cache cleanup**: The apt package lists remain in `/var/lib/apt/lists/`, consuming space. The pip cache remains in `/root/.cache/pip/`.

4. **Full base image**: The `python:3.11` image is based on Debian and includes compilers, development headers, and tools unnecessary for running Python applications.

5. **No version pinning**: Flask, requests, and gunicorn are installed without version specifications, making builds non-reproducible.

Build the image:

```
docker build -t python-api:v1 .
```

### Step 5: Create .NET Application

Create a directory for the .NET application:

```
mkdir -p ~/tools-lab/dotnet && cd ~/tools-lab/dotnet
```

Create the project file. This XML file defines the .NET SDK version and project type:

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

Create a minimal API using .NET 8's top-level statements. This approach requires no controller classes for simple endpoints:

```
cat > Program.cs << 'EOF'
var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();

app.MapGet("/", () => Results.Json(new { service = "dotnet-api", version = "1.0" }));
app.MapGet("/health", () => Results.Json(new { status = "healthy" }));

app.Run("http://0.0.0.0:5000");
EOF
```

Create a Dockerfile that uses the full .NET SDK for the runtime image:

```
cat > Dockerfile << 'EOF'
FROM mcr.microsoft.com/dotnet/sdk:8.0

RUN apt-get update && apt-get install -y vim curl

WORKDIR /app
COPY . .

RUN dotnet restore
RUN dotnet publish -c Release -o out

WORKDIR /app/out
EXPOSE 5000
CMD ["dotnet", "api.dll"]
EOF
```

**Anti-patterns in this Dockerfile:**

1. **SDK in production**: The .NET SDK image (~900MB) includes compilers (Roslyn), MSBuild, and development tools. Production containers only need the ASP.NET runtime (~100MB for Alpine variant).

2. **Source code in image**: The COPY command brings source files into the image. After compilation, these serve no purpose but remain in the layer.

3. **Build artifacts persist**: The `obj/` directory created during restore contains intermediate compilation files that waste space.

4. **No multi-stage build**: A single stage means build dependencies cannot be separated from runtime dependencies.

Build the image:

```
docker build -t dotnet-api:v1 .
```

### Step 6: Create Go Application

Create a directory for the Go application:

```
mkdir -p ~/tools-lab/golang && cd ~/tools-lab/golang
```

Create the Go module file. This declares the module path and Go version:

```
cat > go.mod << 'EOF'
module example/api

go 1.22
EOF
```

Create a web server using Go's standard library. Unlike Python and .NET, Go requires no external web framework for basic HTTP handling:

```
cat > main.go << 'EOF'
package main

import (
    "encoding/json"
    "log"
    "net/http"
)

type Response struct {
    Service string `json:"service"`
    Version string `json:"version,omitempty"`
    Status  string `json:"status,omitempty"`
}

func main() {
    http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
        json.NewEncoder(w).Encode(Response{Service: "go-api", Version: "1.0"})
    })
    http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
        json.NewEncoder(w).Encode(Response{Status: "healthy"})
    })
    log.Fatal(http.ListenAndServe(":8080", nil))
}
EOF
```

Create a single-stage Dockerfile:

```
cat > Dockerfile << 'EOF'
FROM golang:1.22

RUN apt-get update && apt-get install -y vim curl

WORKDIR /app
COPY . .

RUN go build -o server main.go

EXPOSE 8080
CMD ["./server"]
EOF
```

**Anti-patterns in this Dockerfile:**

1. **Entire Go toolchain in production**: The golang image (~800MB) includes the compiler, linker, and standard library sources. A compiled Go binary is self-contained and needs none of these.

2. **Debian-based image**: Go binaries can run on minimal images (Alpine) or even empty images (scratch) when compiled with CGO_ENABLED=0.

3. **Debug symbols included**: By default, Go includes debugging information in binaries. The `-ldflags="-s -w"` flags strip this data, reducing binary size by 20-30%.

4. **Module cache persists**: Downloaded dependencies remain in `/go/pkg/mod/` after compilation.

Build the image:

```
docker build -t go-api:v1 .
```

### Step 7: Record Baseline Image Sizes

Display the sizes of all three images:

```
docker images | grep -E "(python-api|dotnet-api|go-api):v1"
```

Record these values. They represent the unoptimized baseline that subsequent analysis and optimization will improve.

---

## Part 4: Layer Analysis with Dive

Dive provides an interactive terminal interface for exploring image contents. Understanding how to read Dive's output is essential for identifying optimization opportunities.

### Step 8: Analyze the Python Image

Launch Dive against the Python image:

```
dive python-api:v1
```

**Interface layout:**

The screen is divided into two main panels:
- **Left panel (Layers)**: Lists each layer with its size and the command that created it
- **Right panel (Contents)**: Shows the file system state at the selected layer

**Navigation commands:**
- `Tab`: Switch focus between panels
- `↑/↓`: Move selection within the current panel
- `Ctrl+U`: Toggle showing only files that changed in the current layer
- `Space`: Expand or collapse directories
- `Q`: Exit Dive

**Analysis procedure:**

1. Count the layers in the left panel. Each separate RUN command in the Dockerfile created one layer. The Python image should have 9+ layers from the base image plus application layers.

2. Select a layer and press `Tab` to view its contents. Navigate to `/var/lib/apt/lists/` and observe the package manager metadata files. These files enable apt-get to resolve dependencies but serve no runtime purpose.

3. Select the layer created by `apt-get install -y vim curl wget`. Note the size contribution. These tools are not required by the Flask application.

4. Check the pip installation layers. Each `pip install` command created a separate layer, preventing consolidation of the Python package installations.

5. Observe the "Image efficiency score" displayed at the bottom. This percentage indicates how much space is wasted by files that were added in one layer and then modified or removed in later layers.

Press `Q` to exit.

### Step 9: Analyze the .NET Image

Launch Dive against the .NET image:

```
dive dotnet-api:v1
```

**Analysis procedure:**

1. Identify the base image layers. The .NET SDK contributes approximately 800-900MB before any application code is added.

2. Navigate to `/app` in the contents panel. Observe that the source files (Program.cs, api.csproj) exist in the production image despite being unnecessary after compilation.

3. Check `/root/.nuget/packages/`. This directory contains NuGet packages downloaded during restore. These files are not needed at runtime.

4. Locate the `/app/out` directory containing the published application. Note that this output exists alongside the source code rather than replacing it.

5. Examine `/usr/share/dotnet/sdk/`. The entire SDK installation persists in the image even though only the runtime is needed.

Press `Q` to exit.

### Step 10: Analyze the Go Image

Launch Dive against the Go image:

```
dive go-api:v1
```

**Analysis procedure:**

1. Navigate to `/usr/local/go/`. This directory contains the complete Go toolchain: compiler, linker, assembler, and standard library source code. The compiled binary does not require any of these files.

2. Check `/go/pkg/mod/`. This module cache contains downloaded dependencies. After compilation, these are embedded in the binary and the source files are unnecessary.

3. Locate the compiled binary in `/app/server`. Compare its size (a few MB) to the total layer size (hundreds of MB).

4. Observe that Go applications are uniquely suited for minimal images. Unlike Python or .NET, Go compiles to a self-contained binary with no runtime dependencies when CGO is disabled.

Press `Q` to exit.

---

## Part 5: Vulnerability Scanning with Trivy

Trivy scans images by examining the package databases embedded in the image layers. It identifies installed packages, compares their versions against vulnerability databases, and reports known security issues.

### Step 11: Scan the Python Image

Execute a vulnerability scan:

```
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy image python-api:v1
```

**Command breakdown:**
- `--rm`: Remove the Trivy container after the scan completes
- `-v /var/run/docker.sock:/var/run/docker.sock`: Mount the Docker socket to allow Trivy to access local images
- `image python-api:v1`: Specify the image to scan

**Understanding the output:**

Trivy organizes findings by the source of the vulnerability:
- **OS packages (debian)**: Vulnerabilities in packages installed via apt-get
- **Python packages (pip)**: Vulnerabilities in Flask, requests, and their dependencies

Each vulnerability entry contains:
- **Library**: The affected package name
- **Vulnerability**: The CVE (Common Vulnerabilities and Exposures) identifier
- **Severity**: CRITICAL, HIGH, MEDIUM, LOW, or UNKNOWN
- **Installed Version**: The version present in the image
- **Fixed Version**: The version that resolves the vulnerability (if available)

The full Python base image includes hundreds of Debian packages, many of which have known vulnerabilities. Most of these packages are never used by Flask applications but create liability nonetheless.

### Step 12: Scan the .NET Image

```
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy image dotnet-api:v1
```

The .NET SDK image includes development tools, compilers, and debugging utilities. Each of these components may contain vulnerabilities. Additionally, the Debian base layer contributes its own set of vulnerable packages.

Compare the vulnerability count to the Python image. Both use Debian as the base operating system, so they share many of the same OS-level vulnerabilities.

### Step 13: Scan the Go Image

```
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy image go-api:v1
```

The Go image is based on Debian and inherits all Debian vulnerabilities. This is notable because Go applications, unlike Python or .NET applications, can run without any operating system packages. The vulnerabilities exist solely because of the base image choice, not because the application requires the vulnerable packages.

### Step 14: Filter Results by Severity

Production pipelines often need to focus on the most critical issues. Trivy supports severity filtering:

```
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy image --severity CRITICAL,HIGH python-api:v1
```

This command displays only CRITICAL and HIGH severity vulnerabilities, which typically require immediate attention.

### Step 15: Generate Machine-Readable Output

For integration with CI/CD systems, security dashboards, or automated remediation workflows, Trivy can output JSON:

```
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy image --format json python-api:v1 > ~/tools-lab/python-scan.json
```

The JSON output includes detailed metadata about each vulnerability, including CVSS scores, references to advisories, and remediation guidance.

---

## Part 6: Dockerfile Validation with Hadolint

Hadolint parses Dockerfiles and checks each instruction against a set of rules derived from Docker best practices. It also integrates ShellCheck to validate shell commands within RUN instructions.

### Step 16: Lint the Python Dockerfile

```
cd ~/tools-lab/python
docker run --rm -i hadolint/hadolint < Dockerfile
```

**Common findings explained:**

**DL3008 - Pin versions in apt-get install**: Without version pinning, the packages installed depend on the repository state at build time. This makes builds non-reproducible and can introduce unexpected behavior when package versions change.

**DL3009 - Delete the apt-get lists after installing**: The files in `/var/lib/apt/lists/` are used by apt-get to resolve package dependencies. After installation completes, they serve no purpose but consume 20-40MB.

**DL3013 - Pin versions in pip install**: Like apt packages, unpinned pip packages create non-reproducible builds. Version pinning ensures consistent behavior across builds and environments.

**DL3059 - Multiple consecutive RUN instructions**: Each RUN instruction creates a layer. Combining related commands into a single RUN instruction reduces layer count and enables cleanup operations (like removing package lists) to actually reduce image size.

### Step 17: Lint the .NET Dockerfile

```
cd ~/tools-lab/dotnet
docker run --rm -i hadolint/hadolint < Dockerfile
```

Hadolint does not have .NET-specific rules, but it will identify general issues like unpinned apt packages and missing cleanup commands. The fundamental problem with the .NET Dockerfile (using SDK instead of runtime, no multi-stage build) requires human analysis that tools like Dive reveal.

### Step 18: Lint the Go Dockerfile

```
cd ~/tools-lab/golang
docker run --rm -i hadolint/hadolint < Dockerfile
```

Similar to .NET, the Go-specific optimization opportunity (using scratch as the runtime base) is not directly flagged by Hadolint. Hadolint focuses on general Dockerfile hygiene rather than language-specific best practices.

---

## Part 7: Building Optimized Images

Apply the findings from the previous sections to create production-ready images.

### Step 19: Create Optimized Python Image

```
cd ~/tools-lab/python
```

Create an optimized Dockerfile that addresses each identified issue:

```
cat > Dockerfile.optimized << 'EOF'
FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app.py .

RUN pip install --no-cache-dir flask==3.0.0 gunicorn==21.2.0

RUN useradd -r -s /bin/false appuser
USER appuser

EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
EOF
```

**Optimizations applied:**

1. **python:3.11-slim base**: The slim variant excludes compilers, development headers, and documentation. It reduces the base image from ~900MB to ~150MB.

2. **Combined RUN with cleanup**: apt-get update, install, and cleanup occur in a single layer. The `rm -rf /var/lib/apt/lists/*` command removes package metadata, and because it occurs in the same layer as the installation, the space is actually reclaimed.

3. **--no-install-recommends**: Prevents apt from installing recommended but non-essential packages.

4. **--no-cache-dir for pip**: Prevents pip from storing downloaded packages in a cache directory.

5. **Version pinning**: Flask and gunicorn are pinned to specific versions for reproducibility.

6. **Non-root user**: The application runs as an unprivileged user, reducing the impact of potential container escapes.

7. **Production server**: Gunicorn replaces the Flask development server, which is not designed for production traffic.

Build the optimized image:

```
docker build -t python-api:v2 -f Dockerfile.optimized .
```

### Step 20: Create Optimized .NET Image

```
cd ~/tools-lab/dotnet
```

Create a multi-stage Dockerfile that separates build from runtime:

```
cat > Dockerfile.optimized << 'EOF'
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY api.csproj .
RUN dotnet restore
COPY Program.cs .
RUN dotnet publish -c Release -o /app/publish

FROM mcr.microsoft.com/dotnet/aspnet:8.0-alpine
WORKDIR /app
COPY --from=build /app/publish .
RUN adduser -D -s /bin/false appuser
USER appuser
EXPOSE 5000
ENTRYPOINT ["dotnet", "api.dll"]
EOF
```

**Optimizations applied:**

1. **Multi-stage build**: The build stage uses the full SDK to compile the application. The runtime stage uses only the ASP.NET runtime, excluding compilers and build tools.

2. **Alpine-based runtime**: Alpine Linux uses musl libc instead of glibc and includes minimal packages. The ASP.NET Alpine image is approximately 100MB compared to 200MB+ for the Debian variant.

3. **Selective file copying**: Only the published output is copied to the runtime stage. Source code, intermediate build files, and NuGet cache remain in the discarded build stage.

4. **Non-root user**: The application runs as an unprivileged user.

Build the optimized image:

```
docker build -t dotnet-api:v2 -f Dockerfile.optimized .
```

### Step 21: Create Optimized Go Image

```
cd ~/tools-lab/golang
```

Create a multi-stage Dockerfile that produces a minimal image:

```
cat > Dockerfile.optimized << 'EOF'
FROM golang:1.22-alpine AS build
WORKDIR /app
COPY go.mod .
COPY main.go .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o server main.go

FROM scratch
COPY --from=build /app/server /server
EXPOSE 8080
ENTRYPOINT ["/server"]
EOF
```

**Optimizations applied:**

1. **Alpine build stage**: The Alpine-based Go image is smaller than the Debian variant, though the final image size is determined by the runtime stage.

2. **CGO_ENABLED=0**: Disables cgo, which allows Go to link against C libraries. With cgo disabled, the binary is fully statically linked and has no external dependencies.

3. **-ldflags="-s -w"**: The `-s` flag omits the symbol table, and `-w` omits DWARF debugging information. Together they reduce binary size by 20-30%.

4. **scratch base**: The scratch image is empty. It contains no operating system, no shell, no packages. The only content is what you explicitly copy into it.

5. **Zero attack surface**: With no OS packages, there are no packages to have vulnerabilities. Trivy will report zero findings.

Build the optimized image:

```
docker build -t go-api:v2 -f Dockerfile.optimized .
```

### Step 22: Compare Image Sizes

Display all images:

```
docker images | grep -E "(python-api|dotnet-api|go-api)" | sort
```

Expected reductions:
- Python: ~1GB to ~150MB (85% reduction)
- .NET: ~1.2GB to ~110MB (90% reduction)
- Go: ~900MB to ~5MB (99% reduction)

### Step 23: Rescan Optimized Images

Verify that optimization reduced vulnerabilities:

```
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy image python-api:v2
```

```
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy image dotnet-api:v2
```

```
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy image go-api:v2
```

The Go scratch-based image should report zero OS package vulnerabilities. Any vulnerabilities reported are in the Go standard library itself, which is compiled into the binary. This is a significant improvement over the v1 image, which included both OS vulnerabilities and Go stdlib vulnerabilities. The Python and .NET images should show significantly fewer vulnerabilities than their v1 counterparts due to the reduced package count in slim and Alpine base images.

### Step 24: Verify Application Functionality

Confirm that the optimized images work correctly:

```
docker run -d --name test-python -p 5000:5000 python-api:v2
sleep 5
curl http://localhost:5000/health
docker stop test-python && docker rm test-python
```

```
docker run -d --name test-dotnet -p 5001:5000 dotnet-api:v2
sleep 5
curl http://localhost:5001/health
docker stop test-dotnet && docker rm test-dotnet
```

```
docker run -d --name test-go -p 8080:8080 go-api:v2
sleep 5
curl http://localhost:8080/health
docker stop test-go && docker rm test-go
```

All three endpoints should return JSON responses indicating healthy status.

---

## Summary

### Tools and Their Roles

| Tool | Purpose | When to Use |
|------|---------|-------------|
| Dive | Visualize image layer contents and identify wasted space | During development to understand image composition |
| Trivy | Identify known vulnerabilities in OS packages and dependencies | In CI/CD pipelines and as part of registry scanning |
| Hadolint | Validate Dockerfile best practices before building | In pre-commit hooks and code review processes |

### Key Optimization Techniques

1. **Use minimal base images**: slim, Alpine, or distroless variants contain fewer packages and smaller attack surfaces

2. **Implement multi-stage builds**: Separate build-time dependencies from runtime requirements

3. **Consolidate RUN instructions**: Combine related commands to reduce layer count and enable effective cleanup

4. **Clean up in the same layer**: Package manager caches must be removed in the same RUN instruction that creates them

5. **Pin dependency versions**: Explicit versions ensure reproducible builds and easier vulnerability tracking

6. **Run as non-root**: Reduce the impact of container escape vulnerabilities

7. **Consider scratch for compiled languages**: Go and Rust binaries can run in empty images, eliminating all OS package vulnerabilities

## Cleanup

Remove lab artifacts:

```
docker rmi python-api:v1 python-api:v2 dotnet-api:v1 dotnet-api:v2 go-api:v1 go-api:v2 2>/dev/null
rm -rf ~/tools-lab
rm -f dive_*.deb
```
