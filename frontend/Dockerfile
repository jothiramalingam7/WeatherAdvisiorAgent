FROM nginx:alpine

# Remove default configuration file
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx routing rules
COPY nginx.conf /etc/nginx/conf.d/

# Copy static frontend files to nginx doc root
COPY . /usr/share/nginx/html/

# Remove Dockerfile and nginx.conf from doc root to keep it clean
RUN rm -f /usr/share/nginx/html/Dockerfile /usr/share/nginx/html/nginx.conf

EXPOSE 80
