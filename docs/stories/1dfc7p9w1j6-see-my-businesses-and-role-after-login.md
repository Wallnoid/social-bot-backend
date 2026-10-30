## Historia
Como admin de un negocio, quiero iniciar sesión y ver en qué negocio estoy trabajando y mi rol, para saber que estoy en el lugar correcto.

## Criterios de aceptación
- [ ] Dado que pertenezco a un negocio, cuando inicio sesión y pido mi perfil, entonces veo el nombre de ese negocio y mi rol en él.
- [ ] Dado que pertenezco a varios negocios, cuando pido mi perfil, entonces veo cada uno con mi rol en ese negocio, y ninguno al que no pertenezco.
- [ ] Dado que me quitaron de un negocio o ese negocio fue eliminado, cuando pido mi perfil, entonces ese negocio ya no aparece.

## Plan
- El login no cambia: el frontend inicia sesión con JWT y luego pide el perfil.
- El perfil del usuario incluye, solo para lectura, la lista de sus negocios: id, nombre y su rol en cada uno.
- La lista sale únicamente de sus membresías activas y de negocios no eliminados.
- Tests a nivel de API: un negocio, varios negocios sin fugas de otros, y membresía o negocio eliminados.

## Fuera de alcance
- Elegir o cambiar el negocio activo y filtrar datos por negocio (#3).
- Negocios suspendidos (#11): por ahora aparecen como cualquier otro.
- Permisos según el rol (#7).
- Datos del negocio más allá de id, nombre y rol (industria, descripción).
- Limitar la lista a admins: aplica a cualquier miembro (agent, supervisor o admin).

## Sugerencias (tú decides)
- La lista va dentro de `/me` (una sola llamada tras el login); la #3 puede leer del mismo sitio.
