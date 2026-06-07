FROM continuumio/miniconda3:23.11.1-0

WORKDIR /app

# Copy dependency lists first for better cache
COPY requirements.txt /tmp/requirements.txt

# Install runtime conda env with key native deps from conda-forge, then pip install Python deps
RUN conda update -n base -c defaults conda -y && \
    conda create -y -n appenv python=3.10 -c conda-forge dlib numpy pillow cmake && \
    /opt/conda/envs/appenv/bin/pip install --no-cache-dir -r /tmp/requirements.txt && \
    /opt/conda/envs/appenv/bin/pip install --no-cache-dir git+https://github.com/ageitgey/face_recognition_models

ENV PATH=/opt/conda/envs/appenv/bin:$PATH

# Copy app code
COPY . /app

# copy entrypoint and make executable
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["conda","run","-n","appenv","--no-capture-output","gunicorn","-w","4","-b","0.0.0.0:8000","app:app"]
