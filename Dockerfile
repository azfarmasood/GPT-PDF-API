FROM python:3.12

LABEL maintainer="azfar-masood"

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    libjpeg-dev \
    zlib1g-dev \
    poppler-utils \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*\
    && wget https://bin.equinox.io/c/4VmDzA7iaHb/ngrok-stable-linux-amd64.zip \
    && unzip ngrok-stable-linux-amd64.zip -d /usr/local/bin \
    && rm ngrok-stable-linux-amd64.zip

RUN pip install poetry

COPY . /app/

RUN poetry config virtualenvs.create false

RUN poetry install

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libjpeg-dev \
    zlib1g-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 8000

CMD ["poetry", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--reload", "--workers", "2"]


# FROM python:3.12

# LABEL maintainer="azfar-masood"

# WORKDIR /app

# # Install dependencies
# RUN apt-get update && apt-get install -y \
#     build-essential \
#     libpq-dev \
#     tesseract-ocr \
#     libjpeg-dev \
#     zlib1g-dev \
#     poppler-utils \
#     wget \
#     unzip \
#     && rm -rf /var/lib/apt/lists/*

# # Install ngrok
# RUN wget https://bin.equinox.io/c/4VmDzA7iaHb/ngrok-stable-linux-amd64.zip \
#     && unzip ngrok-stable-linux-amd64.zip -d /usr/local/bin \
#     && rm ngrok-stable-linux-amd64.zip

# # Install Poetry
# RUN pip install poetry

# COPY . /app/

# RUN poetry config virtualenvs.create false \
#     && poetry install --no-dev

# EXPOSE 8000

# CMD ["poetry", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--reload", "--workers", "2"]





