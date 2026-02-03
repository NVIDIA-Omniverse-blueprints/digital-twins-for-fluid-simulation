FROM nvcr.io/nvidia/omniverse/ov-base-ubuntu-22:2025.2.0 AS build
USER root
RUN echo "deb https://archive.ubuntu.com/ubuntu/ jammy main restricted universe multiverse" >> /etc/apt/sources.list && \
    echo "deb https://archive.ubuntu.com/ubuntu/ jammy-updates main restricted universe multiverse" >> /etc/apt/sources.list && \
    echo "deb https://archive.ubuntu.com/ubuntu/ jammy-backports main restricted universe multiverse" >> /etc/apt/sources.list && \
    echo "deb https://security.ubuntu.com/ubuntu jammy-security main restricted universe multiverse" >> /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y git git-lfs build-essential libunwind8 && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

COPY kit-app /home/ubuntu/kit-app
COPY build-all.sh /home/ubuntu/build-all.sh
RUN chown -R ubuntu:ubuntu /home/ubuntu/

USER ubuntu
WORKDIR /home/ubuntu
RUN ./build-all.sh

# Final Stage
FROM nvcr.io/nvidia/omniverse/ov-base-ubuntu-22:2025.2.0

USER root
# Create directories and set permissions
RUN mkdir -p /home/ubuntu/.cache/ov && \
    mkdir -p /home/ubuntu/.local/share/ov && \
    mkdir -p /home/ubuntu/usd && \
    mkdir -p /home/ubuntu/.cache/warp

# Copy USD files into the image
COPY rtwt-files/Collected_world_rtwt_Main_v1/ /home/ubuntu/usd/
RUN     chown -R ubuntu:ubuntu /home/ubuntu/.cache && \
chown -R ubuntu:ubuntu /home/ubuntu/.local && \
chown -R ubuntu:ubuntu /home/ubuntu/usd

# Add Ubuntu package repositories and install libunwind8
RUN echo "deb https://archive.ubuntu.com/ubuntu/ jammy main restricted universe multiverse" >> /etc/apt/sources.list && \
    echo "deb https://archive.ubuntu.com/ubuntu/ jammy-updates main restricted universe multiverse" >> /etc/apt/sources.list && \
    echo "deb https://archive.ubuntu.com/ubuntu/ jammy-backports main restricted universe multiverse" >> /etc/apt/sources.list && \
    echo "deb https://security.ubuntu.com/ubuntu jammy-security main restricted universe multiverse" >> /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -qy libunwind8 && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

WORKDIR /scripts
COPY kit-app/scripts/startup.sh /scripts/startup.sh
COPY rtwt-files/demo_data_all/ /data/

WORKDIR /app
COPY --from=build /home/ubuntu/kit-app/_build/packages/*.zip /app
RUN PACKAGE_FILE=$(find /app/. -type f -name "*.zip") && unzip -q $PACKAGE_FILE -d . && rm $PACKAGE_FILE

USER ubuntu
# Open ports for live streaming
EXPOSE 47995-48012/udp \
       47995-48012/tcp \
       49000-49007/udp \
       49000-49007/tcp \
       8011/tcp \
       8111/tcp \
       49100/tcp

ENTRYPOINT ["/scripts/startup.sh"]
