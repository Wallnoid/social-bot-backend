## Historia
Como miembro del equipo de Social Bot, quiero crear un negocio con su primer admin desde el admin de Django, para que un nuevo cliente pueda empezar a usar la suite.

## Criterios de aceptación
- [ ] Dado que estoy en el admin de Django, cuando creo un negocio con su nombre, su industria (de una lista predefinida), una descripción (industria y descripción son opcionales) y el email y nombre de su primer admin, entonces el negocio existe y esa persona es miembro con el rol de admin (sin contraseña todavía).
- [ ] Dado que el email del primer admin ya pertenece a un usuario existente, cuando creo el negocio, entonces ese mismo usuario pasa a ser admin del nuevo negocio y no se crea una cuenta duplicada.
- [ ] Dado que cualquier persona, cuando intenta registrarse por la API o crear, listar o borrar usuarios de otros negocios, entonces la API lo rechaza.

## Plan
- Añadir el negocio (tenant) y la membresía que une a un usuario con un negocio y un rol (agente, supervisor o admin).
- En el admin de Django, un formulario para crear un negocio (nombre, industria de una lista predefinida y descripción) que también pida el email y nombre del primer admin, y que cree el usuario o reutilice el existente.
- Mostrar en el admin los miembros del negocio y sus roles, solo lectura por ahora.
- Desactivar el registro público y retirar de la API los endpoints que listan, crean o borran usuarios de todos los negocios.
- Tests: crear con usuario nuevo, crear con usuario existente y registro rechazado.

## Fuera de alcance
- El email con el enlace para crear la contraseña (historia aparte).
- Mostrar el negocio y el rol tras iniciar sesión (#2), elegir o cambiar de negocio (#3).
- Invitaciones (#4, #5, #12), suspender y reactivar (#11), cuentas de canal (#8).
- Registro autónomo de negocios.

## Sugerencias (tú decides)
- Un usuario sin contraseña no puede entrar hasta usar el enlace. El walking skeleton completo (crear negocio y entrar) queda repartido entre esta historia y la del enlace de contraseña, que conviene hacer seguidas.
