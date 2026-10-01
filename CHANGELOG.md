# Changelog

All notable changes to RemoteSense Toolkit are documented in this file.

The project follows semantic versioning:

`MAJOR.MINOR.PATCH`

---

## [1.0.0] — 2026-10-01

### Added

- Established the first stable release of RemoteSense Toolkit.
- Added modular remote-sensing workflow architecture.
- Added Dataset Import functionality.
- Added AOI creation functionality.
- Added raster clipping functionality.
- Added band extraction and raster statistics functionality.
- Added Band Set / raster combination functionality.
- Added Export and Save functionality.
- Added Satellite Data Explorer & Downloader functionality.
- Added Sentinel-1 GRD dataset discovery.
- Added Sentinel-2 L1C dataset discovery.
- Added Sentinel-2 L2A dataset discovery.
- Added satellite dataset preview and metadata inspection.
- Added CDSE authentication workflow.
- Added satellite dataset downloading.
- Added download progress monitoring.
- Added optional loading of downloaded raster assets into QGIS.
- Added organized QGIS layer grouping for downloaded datasets.
- Added Windows Credential Manager integration for local CDSE credential storage.
- Added project documentation and semantic versioning.

### Improved

- Improved separation between GUI operations, background downloading, and QGIS layer loading.
- Improved handling of authenticated CDSE download requests.
- Improved QGIS raster-layer loading reliability.
- Improved project structure and code organization.

### Security

- CDSE credentials are not stored in source code.
- Authentication credentials are intended to remain outside the Git repository.
- Added Git ignore rules for credential, token, environment, cache, and temporary files.

---

## [0.2.2]

### Fixed

- Fixed missing `QgsApplication` import.
- Removed unnecessary `QgsMessageLog` dependency from plugin startup.

### Improved

- Simplified and hardened Processing provider registration.
- Simplified provider cleanup.
- Kept the main plugin startup independent from Processing provider failures.

---

## [0.2.1]

### Fixed

- Corrected Processing provider registration for QGIS 3.44.

### Added

- Added `hasProcessingProvider=yes` to plugin metadata.

---

## [0.2.0]

### Added

- Added QGIS Processing provider.
- Added Dataset Import algorithm.