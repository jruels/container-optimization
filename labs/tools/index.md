### Lab: Exploring and Securing Docker Images with Dive & Trivy

#### **Introduction**

In this lab, you will use the open-source tools Dive and Trivy to analyze and secure Docker images. Dive is a utility for exploring image layers, identifying inefficiencies, and understanding why some images are larger than others. Trivy is a vulnerability scanner that detects security issues in container images, such as outdated or vulnerable packages. By the end of this lab, you will:

- Understand the purpose and use cases of Dive and Trivy.
- Analyze image structure and efficiency with Dive.
- Scan images for vulnerabilities with Trivy.

### **Section 1: Analyzing Images with Dive**

#### **Purpose of Dive**

Dive helps developers understand how their Docker images are constructed by showing:

- Each layer in the image and its content.
- The size of layers and their impact on the overall image.
- Inefficient practices, such as unoptimized binaries or redundant files.

#### **Steps**

1. **Install Dive**: Install Dive to explore and analyze Docker images.

   ```
   wget https://github.com/wagoodman/dive/releases/download/v0.12.0/dive_0.12.0_linux_amd64.deb
   sudo dpkg -i dive_0.12.0_linux_amd64.deb
   ```

2. **Analyze the Single-Stage Image**: Use Dive to inspect the `docker-gs-ping` image.

   ```
   dive docker-gs-ping
   ```

   - Navigate through the layers using arrow keys.
   - Identify large or inefficient layers and note unnecessary files.

3. **Analyze the Multi-Stage Image**: Use Dive to inspect the `docker-gs-ping:multistage` image.

   ```
   dive docker-gs-ping:multistage
   ```

   - Compare the layer count and size with the single-stage image.
   - Observe how multi-stage builds reduce image size by eliminating unnecessary layers.

4. **Explore Dive Features**:

   - **Efficiency Score**: Pay attention to the score for each layer and overall efficiency.
   - **Comparison**: Compare the efficiency and size of the two images.

5. **Document Observations**:

   - Note the differences in size and structure between the single-stage and multi-stage images.
   - Highlight any inefficiencies discovered in the single-stage image.

### **Section 2: Securing Images with Trivy**

#### **Purpose of Trivy**

Trivy scans container images for vulnerabilities in their dependencies, configurations, and system packages. It is essential for:

- Identifying security issues before deploying images.
- Ensuring compliance with security policies.
- Reducing risk in containerized environments.

#### **Steps**

1. **Understand the Image Structure**:

   - The `docker-gs-ping` image contains a basic web application.
   - The multi-stage version, `docker-gs-ping:multistage`, reduces size by including only runtime dependencies.

2. **Run Trivy on the Single-Stage Image**: Use Trivy to scan for vulnerabilities in the `docker-gs-ping` image.

   ```
   docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v $(pwd):/root/.cache/ aquasec/trivy image docker-gs-ping
   ```

   - Review the output to identify high and critical vulnerabilities.
   - Note any outdated or insecure packages.

3. **Run Trivy on the Multi-Stage Image**: Use Trivy to scan the `docker-gs-ping:multistage` image.

   ```
   docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v $(pwd):/root/.cache/ aquasec/trivy image docker-gs-ping:multistage
   ```

   - Compare the vulnerabilities found in the multi-stage image with the single-stage image.
   - Observe how multi-stage builds reduce attack surface by excluding development dependencies.

4. **Explore Trivy Features**:

   - **Severity Levels**: Understand how vulnerabilities are categorized (e.g., Critical, High, Medium).
   - **Output Details**: Review detailed descriptions and recommendations for fixing issues.

5. **Document Observations**:

   - Note the vulnerabilities in each image.
   - Reflect on how multi-stage builds and regular scanning improve security.

### **Conclusion**

By completing this lab, you have learned how to analyze Docker images for efficiency using Dive and secure them by detecting vulnerabilities with Trivy. These tools are crucial for:

- Optimizing image size and structure.
- Ensuring that containerized applications are secure and production-ready.

Leverage Dive and Trivy in your development workflow to build efficient, secure, and reliable Docker images.