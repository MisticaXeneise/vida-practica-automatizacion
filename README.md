# Vida Práctica — automatización de Instagram

Este repositorio contiene exclusivamente la automatización de **Vida Práctica** para la cuenta de Instagram **@vidapractica_hoy**.

## Publicaciones programadas
- 2 Reels por día.
- 5 Stories por día.
- 1 carrusel por día.

Los materiales se seleccionan desde el inventario de Google Drive y se publican mediante Instagram Graph API. El historial se conserva en la rama `vida-practica-state` para evitar repetir contenido y duplicar publicaciones.

## Configuración necesaria
En **Settings → Secrets and variables → Actions**, agregar los cuatro secretos:

- `VIDA_PRACTICA_CLOUDINARY_CLOUD_NAME`
- `VIDA_PRACTICA_CLOUDINARY_API_KEY`
- `VIDA_PRACTICA_CLOUDINARY_API_SECRET`
- `VIDA_PRACTICA_INSTAGRAM_TOKEN`

No guardar tokens ni claves en archivos del repositorio.

El workflow usa `GITHUB_TOKEN` automáticamente, con permiso `contents: write`, para persistir el historial.

## Prueba manual
En **Actions → Vida Practica - publicador integrado → Run workflow**, seleccionar un horario y el modo `dry_run`. La prueba valida Drive, descarga de archivos y Cloudinary, sin publicar en Instagram.

Para publicar manualmente, seleccionar `publicar`. El modo programado publica automáticamente en los horarios definidos.

## Zona horaria
Los horarios están expresados para Argentina (UTC-3). GitHub Actions recibe los cron en UTC.

## Seguridad
Este repositorio es público. Las credenciales deben permanecer exclusivamente en GitHub Actions Secrets.
