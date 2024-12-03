### Lab: Building Smaller Images with Multi-Stage Builds 

#### **Introduction**
In this lab, you will explore the concept of multi-stage builds in Docker. By the end of the lab, you will understand how to reduce image size by utilizing multi-stage builds. This lab inspects images, creates multi-stage builds, and compares image sizes and layers.

#### **Lab Objectives**
- Inspect a Docker image and analyze its size and layers.
- Convert a single-stage Dockerfile into a multi-stage Dockerfile.
- Compare the resulting images in terms of size and number of layers.

---

#### **Task 1: Inspect the Original Image**
1. **Access the Server**: Log in to the provided server using SSH credentials.
2. **Clone the lab repository**: `git clone https://github.com/jruels/container-security ~/container-security`
3. **Create a lab directory**: `mkdir ~/lab-multi`
4. **Enter the lab directory**: `cd ~/lab-multi`
5. **Copy the lab files from the repo**: `cp -r ~/container-security/labs/multi-stage/src/* .`



## Sample Go application

The example application is a simple microservice. It is purposefully trivial to keep focus on learning the basics of containerization for Go applications.

The application offers two HTTP endpoints:

- It responds with a string containing a heart symbol (`<3`) to requests to `/`.
- It responds with `{"Status" : "OK"}` JSON to a request to `/health`.

It responds with HTTP error 404 to any other request.

The application listens on a TCP port defined by the value of the environment variable `PORT`. The default value is `8080`.

The application is stateless.



## Dockerfile for the application

Review the `Dockerfile` in the lab directory. 

```dockerfile
# syntax=docker/dockerfile:1

FROM golang

# Set destination for COPY
WORKDIR /app

# Download Go modules
COPY go.mod go.sum ./
RUN go mod download

# Copy the source code. Note the slash at the end, as explained in
# https://docs.docker.com/reference/dockerfile/#copy
COPY *.go ./

# Build
RUN CGO_ENABLED=0 GOOS=linux go build -o /docker-gs-ping

# Optional:
# To bind to a TCP port, runtime parameters must be supplied to the docker command.
# But we can document in the Dockerfile what ports
# the application is going to listen on by default.
# https://docs.docker.com/reference/dockerfile/#expose
EXPOSE 8080

# Run
CMD ["/docker-gs-ping"]
```



## Build the image

Now that you've reviewed the `Dockerfile` build an image from it. The `docker build` command creates Docker images from the `Dockerfile` and a context. A build context is the set of files in the specified path or URL. The Docker build process can access any files in the context.

The build command optionally takes a `--tag` with shorthand as `-t`  flag. This flag labels the image with a string value, which is easy for humans to read and recognize. If you don't pass a `--tag`, Docker will use `latest` as the default value.



```console
$ docker build -t docker-gs-ping .
```

The build process will print some diagnostic messages through the build steps. Your exact output will vary, but provided there aren't any errors, you should see the word `FINISHED` in the first line of output. This means Docker has successfully built your image named `docker-gs-ping`.



## View image details

To list images, run the `docker image ls` command (or the `docker images` shorthand):



```console
$ docker image ls

REPOSITORY                       TAG       IMAGE ID       CREATED         SIZE
docker-gs-ping                   latest    7f153fbcc0a8   2 minutes ago   1.11GB
...
```

Your exact output may vary, but you should see the `docker-gs-ping` image with the `latest` tag. Because you didn't specify a custom tag when you built your image, Docker assumed the tag would be `latest`.



## Multi-stage builds

You may have noticed that your `docker-gs-ping` image weighs in at over a gigabyte, which is a lot for a tiny compiled Go application. You may also wonder what happened to the full suite of Go tools, including the compiler, after you built your image.

The answer is that the entire toolchain is still in the container image. This is inconvenient because of the large file size, but it may also present a security risk when the container is deployed.

These two issues can be solved by using multi-stage builds.

In summary, a multi-stage build can carry over the artifacts from one build stage to another, and each build stage can be instantiated from a different base image.

Thus, you will build your application using a full-scale official Go image in the following example. Then, you'll copy the application binary into another image whose base is lean and doesn't include the Go toolchain or other optional components.

The `Dockerfile.multistage` in the sample application's repository has the following content:



```dockerfile
# syntax=docker/dockerfile:1

# Build the application from source
FROM golang:1.19 AS build-stage

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY *.go ./

RUN CGO_ENABLED=0 GOOS=linux go build -o /docker-gs-ping

# Run the tests in the container
FROM build-stage AS run-test-stage
RUN go test -v ./...

# Deploy the application binary into a lean image
FROM gcr.io/distroless/base-debian11 AS build-release-stage

WORKDIR /

COPY --from=build-stage /docker-gs-ping /docker-gs-ping

EXPOSE 8080

USER nonroot:nonroot

ENTRYPOINT ["/docker-gs-ping"]
```

Since you have two Dockerfiles now, you must tell Docker what Dockerfile you'd like to use to build the image. Tag the new image with `multistage`. 



```console
$ docker build -t docker-gs-ping:multistage -f Dockerfile.multistage .
```

Comparing the sizes of `docker-gs-ping:multistage` and `docker-gs-ping:latest` you see a significant difference.



```console
$ docker image ls
REPOSITORY       TAG          IMAGE ID       CREATED              SIZE
docker-gs-ping   multi        4354e949d028   About an hour ago    29.3MB
docker-gs-ping   latest       e7777990002a   2 hours ago          1.02GB
```

This is so because the "distroless" base image you used in the second stage of the build is very barebones and designed for lean deployments of static binaries.



## Challenge

There's much more to multi-stage builds, including using `scratch` as your runtime base image. As a challenge, modify your `Dockerfile` to statically link the Go application and use the `scratch` base image. 



## Congratulations

Congratulations on completing the lab! You learned how to inspect Docker images, convert a single-stage Dockerfile into a multi-stage build, and leverage lightweight runtime images to reduce image size significantly. By applying these skills, you created a lean, optimized image, improving efficiency and security. 
