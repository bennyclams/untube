FROM python:3.8

RUN mkdir /app
WORKDIR /app

RUN apt update && apt install -y ffmpeg
COPY . /app
RUN pip install -r requirements.txt
ENTRYPOINT [ "gunicorn", "-b 0.0.0.0", "--workers=8", "--threads=6", "--chdir", "/app", "adless.web:app" ]
