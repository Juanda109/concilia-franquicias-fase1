FROM nginx:alpine

COPY public/ /usr/share/nginx/html/
COPY nginx.container.conf /etc/nginx/conf.d/default.conf

# Solo se dan permisos a cache, config y tmp
RUN chgrp -R 0 /var/cache/nginx /etc/nginx /tmp && \
    chmod -R g+rwX /var/cache/nginx /etc/nginx /tmp

EXPOSE 8080