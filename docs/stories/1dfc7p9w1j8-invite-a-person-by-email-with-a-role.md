## Historia
Como admin de un negocio, quiero invitar a una persona por email con un rol (agent, supervisor o admin), y que la invitación caduque a la semana, para que mi equipo pueda entrar al negocio sin dejar invitaciones abiertas para siempre.

## Criterios de aceptación
- [ ] Dado que soy admin del negocio activo, cuando invito un email con un rol, entonces esa persona recibe un email con un enlace para unirse a ese negocio con ese rol, que indica cuándo caduca (7 días por defecto).
- [ ] Dado que soy agent o supervisor del negocio activo, cuando intento invitar a alguien, entonces la API lo rechaza.
- [ ] Dado que el email ya es miembro de ese negocio o ya tiene una invitación pendiente en él, cuando lo invito, entonces la API lo rechaza con un mensaje claro.

## Plan
- Un registro de invitación por negocio con email, rol, quién invitó, un token de un solo uso y la fecha de caducidad, calculada con un valor del `.env` (7 días por defecto).
- Un endpoint para el admin del negocio activo (`X-Tenant-ID`) que valida el email y el rol, crea la invitación y envía el email con el enlace `{FRONTEND_URL}/accept-invitation?token=…`.
- Solo un admin del negocio activo puede invitar; agent y supervisor reciben un rechazo.
- Se rechaza invitar a quien ya es miembro activo o tiene una invitación pendiente sin caducar en ese negocio.
- Si el email no se puede enviar, la API responde con error y la invitación no se guarda.

## Fuera de alcance
- Aceptar la invitación, con cuenta nueva o existente (#5).
- Cancelar una invitación pendiente (#12).
- Listar las invitaciones pendientes del negocio.
- Reenviar una invitación caducada.
- Permisos por rol en el resto de la API (#7): aquí solo se comprueba que quien invita es admin.

## Decisiones tomadas
- La caducidad es configurable en el `.env`, con 7 días por defecto.
- Se rechaza invitar a un miembro activo o a un email con invitación pendiente sin caducar.
- Sin email enviado no hay invitación: una invitación que nadie recibió no sirve de nada.
