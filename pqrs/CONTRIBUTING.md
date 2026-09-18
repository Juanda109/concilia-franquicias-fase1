# Contribuciones

¡Gracias por tu interés en contribuir a este proyecto! Agradecemos cualquier contribución que se alinee con nuestros objetivos y pautas del proyecto.

## Empezando 🚀
Para comenzar a contribuir, sigue estos pasos:
1. Haz un fork del repositorio.
2. Crea una nueva rama para tus cambios.
3. Realiza los cambios deseados.
4. Prueba tus cambios para asegurarte de que funcionen como se espera.
5. Haz commit de tus cambios y súbelos a tu repositorio.
6. Envía una _Pull Request_ al repositorio principal.

## Pautas 💠
Ten en cuenta las siguientes pautas al contribuir:
- Sigue el estilo de codificación y las convenciones utilizadas en el proyecto.
- Escribe mensajes de commit claros y concisos.
- Incluye pruebas para cualquier nueva funcionalidad o corrección de errores.
- Sé respetuoso y considerado con otros colaboradores.

### Mensajes de Commit Semánticos 👌
Observa cómo un cambio menor en el estilo de tus mensajes de commit puede hacerte un mejor programador.

Formato: `<type>(<scope>): [issue] <subject>`
`<issue>` Historia de usuario o código de ticket de la herramienta de seguimiento relacionado con el cambio que vas a commitear.
`<scope>` es opcional. Si tu cambio es específico de uno o dos paquetes, considera agregar el alcance. Los alcances deben ser breves pero reconocibles, por ejemplo, `content-docs`, `theme-classic`, `core`.

Los diferentes tipos de commits son:
- `feat`: una nueva API o comportamiento **para el usuario final**.
- `fix`: una corrección de errores **para el usuario final**.
- `docs`: un cambio en el sitio web u otros documentos Markdown en nuestro repositorio.
- `refactor`: un cambio en el código de producción que no genera diferencias en el comportamiento, por ejemplo, dividir archivos, cambiar nombres de variables internas, mejorar el estilo del código...
- `test`: agregar pruebas faltantes, refactorizar pruebas; sin cambios en el código de producción.
- `chore`: actualizar dependencias, lanzar nuevas versiones... Tareas que se realizan **regularmente** con fines de mantenimiento.
- `misc`: cualquier otra cosa que no cambie el código de producción, pero no sea `test` o `chore`, por ejemplo, actualizar el pipeline de construcción del proyecto.

Ejemplo:
```
feat(core): [JIRA02-33] Permitir la anulación de la configuración de webpack
^--^^----^  ^---------^ ^------------^
|   |       |           |
|   |       |           +-> Resumen en tiempo presente. ¡Usa minúsculas en lugar de mayúsculas!
|   |       |
|   |       +-> Código de historia de usuario.
|   |
|   +-> El/los paquete(s) que se ven afectados por este cambio.
|
+-------> Tipo: consulta la lista que usamos arriba.

```

## Versionado 📌
Usamos [SemVer](http://semver.org/) para el versionado. Para todas las versiones disponibles, mira los [tags en este repositorio](https://github.com/tu/proyecto/tags).

Agradecemos tus contribuciones y esperamos trabajar contigo!



