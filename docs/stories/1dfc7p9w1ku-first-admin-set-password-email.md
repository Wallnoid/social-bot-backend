## Historia
Como primer admin de un negocio, quiero recibir un email con un enlace para crear mi contraseña, para poder entrar por primera vez a la suite.

## Criterios de aceptación
- [ ] Dado que el equipo de Social Bot crea un negocio con un primer admin que no tiene contraseña, cuando se guarda el negocio, entonces esa persona recibe un email con un enlace para crear su contraseña.
- [ ] Dado que tengo un enlace válido, cuando creo mi contraseña con él, entonces puedo iniciar sesión con mi email y esa contraseña, y el enlace deja de funcionar.
- [ ] Dado que el enlace ya se usó o caducó, cuando intento crear la contraseña con él, entonces la API lo rechaza con un mensaje claro.

## Plan
- Al crear el negocio, si el primer admin no tiene contraseña usable, enviarle un email con un enlace al frontend que lleve un token de un solo uso que caduca a los 7 días. Si ya tiene contraseña, no se envía nada.
- Un endpoint público de la API que recibe el token y la nueva contraseña, la valida con las reglas de contraseña de Django y la guarda.
- La URL del frontend va en una variable de entorno (`FRONTEND_URL`); mientras no exista, queda un valor provisional en el `.env`.
- El envío usa la configuración de email que ya existe: consola en local y SMTP en producción, con el buzón `contact@wanps.tech` de Hostinger.
- Tests: email enviado con el enlace, contraseña creada e inicio de sesión correcto, enlace usado o caducado rechazado, y sin email si el usuario ya tiene contraseña.

## Fuera de alcance
- Reenviar el email si caduca o se pierde.
- La pantalla del frontend que recibe el enlace (es otro proyecto).
- El diseño del email (texto plano por ahora).
- "Olvidé mi contraseña" para usuarios que ya tienen una.
- Aceptar invitaciones (#5), aunque reutilizará este mecanismo.

## Sugerencias (tú decides)
- Django ya trae un generador de tokens de un solo uso para restablecer contraseñas, que deja de valer en cuanto cambia la contraseña. Usarlo evita crear modelo y migración propios para el token, y la #5 puede reutilizarlo.
- Los datos SMTP del buzón de Hostinger (servidor, puerto y cifrado) hay que tomarlos de su panel. La configuración de producción actual usa STARTTLS en el puerto 587 con Gmail por defecto; si Hostinger exige SSL en el 465, habrá que añadir esa opción. La contraseña del buzón va solo en variables de entorno.
