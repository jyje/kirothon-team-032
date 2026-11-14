# syntax=docker/dockerfile:1
# Placeholder image: serves a static page until the project has app code.
# shortcut: static nginx page only, replace with the app build when code lands.
FROM nginxinc/nginx-unprivileged:1.27-alpine

COPY ./html/ /usr/share/nginx/html/

# Unprivileged nginx listens on 8080 and runs as a non-root user.
EXPOSE 8080
