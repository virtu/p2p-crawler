FROM python:3.9-slim-bullseye

WORKDIR /usr/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src .

ARG BUILD_TIME=unknown
ARG BUILD_VERSION=unknown
ARG BUILD_GIT_BRANCH=unknown
ARG BUILD_GIT_COMMIT=unknown
ARG BUILD_GIT_STATUS=unknown

RUN echo "$BUILD_TIME" > /build-time.txt && \
    echo "$BUILD_VERSION" > /build-version.txt && \
    echo "$BUILD_GIT_BRANCH" > /build-git-branch.txt && \
    echo "$BUILD_GIT_COMMIT" > /build-git-commit.txt && \
    echo "$BUILD_GIT_STATUS" > /build-git-status.txt

CMD ["python", "run.py"]
