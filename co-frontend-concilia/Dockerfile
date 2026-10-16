FROM nginx:alpine

# 1. Crear el usuario appuser con UID 10001 (UID > 1000 por buenas prácticas)
# y asignarle el grupo principal 0 (root) requerido por OpenShift
RUN adduser -D -u 10001 -G root appuser

# Copiar el contenido de la app y la configuración de nginx para OKD
COPY public/ /usr/share/nginx/html/
COPY nginx.container.conf /etc/nginx/conf.d/default.conf

# 2. Modificar la ruta del PID hacia /tmp (donde cualquier usuario tiene permisos de escritura)
# y comentar la directiva 'user' para evitar advertencias
RUN sed -i 's|/var/run/nginx.pid|/tmp/nginx.pid|g' /etc/nginx/nginx.conf \
    && sed -i 's|/run/nginx.pid|/tmp/nginx.pid|g' /etc/nginx/nginx.conf \
    && sed -i 's/^user /# user /' /etc/nginx/nginx.conf

# 3. Asignar propiedad de carpetas a appuser y dar permisos al grupo 0 (root)
# OpenShift asigna UIDs aleatorios pertenecientes al grupo 0 (root)
RUN chown -R appuser:0 /var/cache/nginx \
                       /var/log/nginx \
                       /etc/nginx \
                       /usr/share/nginx/html \
                       /tmp \
    && chmod -R g+rwX /var/cache/nginx \
                      /var/log/nginx \
                      /etc/nginx \
                      /usr/share/nginx/html \
                      /tmp

# 4. Cambiar puerto por defecto: los usuarios no-root no pueden escuchar en puertos < 1024
RUN sed -i 's/listen  *80;/listen 8080;/g' /etc/nginx/conf.d/default.conf

# 5. Cambiar al usuario appuser
USER 10001

EXPOSE 8080
