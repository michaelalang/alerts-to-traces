# OpenShift AlertManager Alerts webhook to traces

This small service provides the possibility to convert Alerts in OpenShift created by AlertManager in openshift-monitoring to traces and
visualize them in the Observ -> Trace UI.

## Requirements

* OpenShift 4.16+ (tested on 16,17,18)
* OpenShift Cluster Observability Operator 
    * UI Plugin Traces 


## Prepare 

### Building the Image 

The image is based upon Fedora41 and python3.13. The Dockerfile included provides a minimal image at the end by using a multi-stage
build process ([OpenSourcerers Article](https://www.opensourcerers.org/2025/01/27/lower-your-container-image-size-and-improve-compliance/))

* build and push the image with 
    ```
    podman build -f Dockerfile -t your-registry/your-repo/image:tag
    podman push your-registry/your-repo/image:tag
    ```


## Creating the deployment

The `deploy` directory contains the necessary CR's to deploy the webhook receiver. It also utilizes the opentelemetry contrib collector to
forward syslog to Loki (no included). 

* ensure to update the `kustomization.yaml` file with:
    * the `namespace` you want to deploy the service to
    * the `image name` and `tag` you build the code to

* after adjustin the `kustomization.yaml` file prep and verify the CR's with
    ```
    export NAMESPACE=... # necessary to ensure all resources are aligned (RBAC, Alertmanager config)
    kustomize build deploy | envsubst 
    ```

* ensure that all `${NAMESPACE}` variables have been replaced accordingly

* if you are comfortable deploy the service with 
    ```
    kustomize build deploy | envsubst | oc -n ${NAMESPACE} apply -k deploy
    ``` 

* verify that the deployment has been started succesfully 
    ```
    oc -n ${NAMESPACE} get pod,service,secret
    ```

## Adjusting the AlertManager webhook configuration

I included a default AlertManager secret config from an 4.16 Cluster but feel free to use the UI to update the Alert receivers to the webhook 
address as well.

* create the AlertManager secret with
    ```
    oc -n openshift-monitoring create secret generic alertmanager-main \
      --from-literal=alertmanager.yaml="$(envsubst < deploy/alertmanager.yaml)" --dry-run=client -o yaml |
    oc -n openshift-monitoring replace -f -
    ```

## Test the deployment

```
oc -n ${NAMESPACE} port-forward service/alert-receiver 8080:8080 & 

curl -X POST -d @alert.json \
  -H "Content-Type: application/json" 
  localhost:8080/webhook/alert-receiver
 -v -H "x-forwarded-for: 10.11.12.13"
```

Example output
```
*   Trying 127.0.0.1:8080...
* Connected to localhost (127.0.0.1) port 8080 (#0)
> POST /webhook/alert-receiver HTTP/1.1
> Host: localhost:8088
> User-Agent: curl/7.76.1
> Accept: */*
> Content-Type: application/json
> x-forwarded-for: 10.11.12.13
> Content-Length: 8080
> 
* Mark bundle as not supporting multiuse
< HTTP/1.1 201 Created
< traceparent: 00-6ee609f90f8aa746acaf675e338b2e82-727434c82cb13d7d-01
< Content-Length: 0
< Date: Sun, 22 Jun 2025 08:15:46 GMT
< Server: Python/3.13 aiohttp/3.12.13
< 
* Connection #0 to host localhost left intact
```
