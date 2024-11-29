# Install Kubernetes on AWS
## Install Kubernetes on all servers

Run the following commands on **all** servers.
Following commands must be run as the root user. To become root run: 
```
sudo su - 
```

Install packages required for Kubernetes on all servers as the root user
```
# If the folder `/etc/apt/keyrings` does not exist, it should be created before the curl command, read the note below.
# sudo mkdir -p -m 755 /etc/apt/keyrings
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.29/deb/Release.key | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
```

Create Kubernetes repository by running the following as one command.
```
echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.29/deb/ /' | sudo tee /etc/apt/sources.list.d/kubernetes.list
```

Now that you've added the repository install the packages
```
sudo apt-get update
sudo apt-get install -y kubelet kubeadm kubectl
sudo apt-mark hold kubelet kubeadm kubectl
```

The kubelet is now restarting every few seconds, as it waits in a `crashloop` for `kubeadm` to tell it what to do.

### Install the Docker CRI Shim
Kubernetes requires a CRI compliant runtime, but Docker is not one by default. To get around this the community has developed a compatibility shim. 
Download the `cri-dockerd` package 
```
wget https://github.com/Mirantis/cri-dockerd/releases/download/v0.3.11/cri-dockerd_0.3.11.3-0.ubuntu-jammy_amd64.deb
```

Install the package
```
dpkg -i cri-dockerd_0.3.11.3-0.ubuntu-jammy_amd64.deb
```

Confirm the service is running 
```
systemctl status cri-docker
```

If it is not running, execute the following 
```
systemctl start cri-docker 
systemctl enable cri-docker
```


### Initialize the Master 
Run the following command on the master node to initialize 
```
kubeadm init --ignore-preflight-errors=all --cri-socket=unix:///var/run/cri-dockerd.sock
```

If everything was successful output will contain 
````
Your Kubernetes master has initialized successfully!
````

Note the `kubeadm join...` command, it will be needed later on.

Exit to ubuntu user 
```
exit
```

Now configure server so you can interact with Kubernetes as the unprivileged user. 
```
mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config
```

Run following on the master to enable IP forwarding to IPTables.
```
sudo sysctl net.bridge.bridge-nf-call-iptables=1
```

### Pod overlay network
Install a Pod network on the master node
```
kubectl apply -f https://github.com/weaveworks/weave/releases/download/v2.8.1/weave-daemonset-k8s.yaml
```

Wait until `coredns` pod is in a `running` state
```
kubectl get pods -n kube-system
```

### Join nodes to cluster 
Log into each of the worker nodes and run the join command from `kubeadm init` master output. 
```
sudo kubeadm join <command from kubeadm init output> --ignore-preflight-errors=all --cri-socket=unix:///var/run/cri-dockerd.sock
```

To confirm nodes have joined successfully log back into master and run 
```
kubectl get nodes -w
````

When they are in a `Ready` state the cluster is online and nodes have been joined. 

To stop watching type `ctrl+c`

# Congrats! 
