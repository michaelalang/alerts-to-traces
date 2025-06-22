FROM quay.io/fedora/fedora as base

RUN dnf -y install --setopt=tsflags=nodocs --setopt=install_weak_deps=0 --nodocs\
      python3.13-devel autoconf automake bzip2 gcc-c++ gd-devel gdb git libcurl-devel \
      libpq-devel libxml2-devel libxslt-devel lsof make mariadb-connector-c-devel \
      openssl-devel patch procps-ng npm redhat-rpm-config sqlite-devel unzip wget which zlib-devel \
      python3.13-pip ; \
      yum -y clean all --enablerepo='*'

FROM base as builder
COPY requirements.txt /tmp/requirements.txt
RUN dnf -y --setopt=install_weak_deps=0 --nodocs --use-host-config \
      --installroot /output \
      install \
      glibc glibc-minimal-langpack libstdc++ \
      bash \
      python3.13 python3.13-requests python3.13-dateutil python3.13-packaging ; \
      yum -y clean all --enablerepo='*'

RUN pip3.13 install --prefix=/usr --root /output -r /tmp/requirements.txt

FROM scratch 

COPY --from=builder /output / 
# should be included but Fedora41 does not provide buildinfo
#COPY --from=base /root/buildinfo /root/buildinfo
COPY app.py /opt/app/app.py
COPY a2t /opt/app/a2t

USER 1001
WORKDIR /opt/app
ENTRYPOINT [ "/usr/bin/gunicorn" ]
CMD [ "--pythonpath", "/usr/bin/python3.13", "--bind", "0.0.0.0:8080", "app:app_factory", "--worker-class", "aiohttp.GunicornWebWorker", "--access-logfile", "-"]
