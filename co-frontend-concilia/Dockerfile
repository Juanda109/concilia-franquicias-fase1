FROM nginx:alpine
COPY public/ /usr/share/nginx/html/
COPY nginx.container.conf /etc/nginx/conf.d/default.conf

# SCC restringida de OKD: corre con un UID arbitrario, pero siempre en el
# grupo 0. nginx:alpine por defecto deja estos directorios de root:root,
# así que sin esto el proceso no puede escribir su pid/cache y falla al
# arrancar bajo esa SCC.
RUN chgrp -R 0 /var/cache/nginx /etc/nginx && chmod -R g+rwX /var/cache/nginx /etc/nginx
RUN touch /var/run/nginx.pid && chgrp 0 /var/run/nginx.pid && chmod g+rw /var/run/nginx.pid

EXPOSE 8080
