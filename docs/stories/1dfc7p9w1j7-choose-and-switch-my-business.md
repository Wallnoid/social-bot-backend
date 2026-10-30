## Historia
Como usuario que pertenece a varios negocios, quiero elegir y cambiar el negocio en el que trabajo, para ver solo los datos de ese negocio.

## Criterios de aceptación
- [ ] Dado que pertenezco a varios negocios, cuando indico en una petición con cuál quiero trabajar, entonces la API trabaja en ese negocio y me muestra cuál es y mi rol en él; y si indico otro, trabaja en el otro.
- [ ] Dado que indico un negocio al que no pertenezco, que me quitaron o que fue eliminado, cuando hago la petición, entonces la API la rechaza como si ese negocio no existiera.
- [ ] Dado que pertenezco a varios negocios y no indico ninguno, cuando hago la petición, entonces la API me pide elegir uno (y si pertenezco a uno solo, trabaja en ese sin que yo lo indique).

## Plan
- El frontend indica el negocio activo en cada petición con una cabecera (`X-Tenant-ID`). Cambiar de negocio es mandar otro id; no se guarda nada en el servidor.
- El backend comprueba en cada petición que el usuario tiene una membresía activa en un negocio no eliminado; si no, responde como si no existiera.
- El negocio activo y el rol del usuario quedan disponibles para el resto de la API, para que las historias siguientes filtren sus datos con ellos.
- Un endpoint mínimo (`GET /api/v1/tenants/current/`) devuelve el negocio activo y mi rol, para poder verificar el mecanismo de punta a punta.
- Tests a nivel de API: negocio elegido, otro negocio, negocio ajeno, removido o eliminado, sin indicar con varios, y con uno solo.

## Fuera de alcance
- Filtrar datos reales por negocio (contactos, conversaciones, canales): llega con la #8 y la #10, que usarán este mecanismo.
- Permisos según el rol (#7).
- Negocios suspendidos (#11): por ahora se comportan como cualquier otro.
- Recordar el último negocio usado entre sesiones.

## Decisiones tomadas
- El negocio activo va en la cabecera `X-Tenant-ID` (no en el token JWT), para no tocar el login y poder tener dos negocios abiertos en dos pestañas.
- Con varios negocios y sin indicar ninguno, la API responde con un error que pide elegir; nunca toma uno por defecto.
- El endpoint mínimo es propio (`tenants/current/`), no parte de `/me`.
