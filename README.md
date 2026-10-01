# RemoteSense Toolkit

**RemoteSense Toolkit** is a modular QGIS plugin for exploring, importing, downloading, organizing, and processing remote sensing datasets.

The project is designed as an extensible remote-sensing workflow inside QGIS, with individual modules responsible for different stages of the data-processing pipeline.

---

## Version

**1.0.0**

**Author:** Punithan  
**Platform:** QGIS  
**Minimum QGIS Version:** 3.28  
**License:** MIT

---

## Overview

RemoteSense Toolkit is being developed as a modular remote-sensing environment for QGIS.

The toolkit is intended to support the workflow from raw satellite-data discovery and import through preprocessing, feature generation, classification, accuracy assessment, and reporting.

The architecture is organized into independent modules so that individual processing stages can be developed, tested, and extended without unnecessarily modifying stable components.

---

## Current Features

### 01 — Dataset Import

The Dataset Import module allows remote-sensing raster datasets to be imported into a QGIS project.

It can:

1. Accept a folder containing raster datasets.
2. Scan supported raster formats.
3. Optionally search subfolders recursively.
4. Validate raster datasets through QGIS/GDAL.
5. Read basic raster metadata.
6. Load valid rasters into the current QGIS project.
7. Produce an import report.

Supported raster extensions include:

- `.tif`
- `.tiff`
- `.jp2`
- `.img`
- `.vrt`
- `.nc`

---

### 02 — AOI Creation

The AOI module provides functionality for creating a study-area boundary for subsequent remote-sensing operations.

The AOI can be used as the spatial extent for later clipping, extraction, and dataset-processing operations.

---

### 03 — Raster Clipping

The Raster Clipping module provides raster clipping using a defined spatial extent/AOI.

It is intended to reduce large remote-sensing datasets to the area required for analysis.

---

### 04 — Band Extraction and Raster Statistics

This module provides tools for extracting raster bands and obtaining basic raster statistics.

The module is designed to support subsequent raster preprocessing and feature-generation workflows.

---

### 05 — Band Set / Raster Combination

The Band Set module provides functionality for organizing multiple raster bands into a combined dataset for subsequent remote-sensing analysis.

This provides a foundation for multispectral and multi-band workflows.

---

### 06 — Export and Save

The Export and Save functionality provides a controlled way to save and export generated raster datasets and related outputs.

---

### 07 — Satellite Data Explorer & Downloader

Module 07 provides satellite-data discovery and downloading functionality through the **Copernicus Data Space Ecosystem (CDSE)**.

Current supported missions/data collections include:

- **Sentinel-1 GRD**
- **Sentinel-2 L1C**
- **Sentinel-2 L2A**

The module provides functionality for:

- Satellite dataset search
- Acquisition-date filtering
- AOI-based searching
- Sentinel-1 acquisition filtering
- Polarization selection
- Orbit-direction selection
- Dataset metadata inspection
- Asset inspection
- Dataset preview
- CDSE authentication
- Satellite-data downloading
- Download progress monitoring
- Optional loading of downloaded raster assets into QGIS
- Organized QGIS layer grouping

Downloaded datasets can be kept as files without automatically loading them into QGIS.

---

## Satellite Data Sources

### Copernicus Data Space Ecosystem

Module 07 currently uses the Copernicus Data Space Ecosystem for satellite-data discovery and downloading.

Current supported collections:

| Mission | Product / Collection | Status |
|---|---|---|
| Sentinel-1 | GRD | Implemented |
| Sentinel-2 | L1C | Implemented |
| Sentinel-2 | L2A | Implemented |

Additional satellite missions and product types are planned for future releases.

---

## Remote-Sensing Workflow

The long-term workflow of RemoteSense Toolkit is structured around the following stages:

```text
Dataset Discovery
       ↓
Dataset Import
       ↓
AOI / Study Area
       ↓
Dataset Download / Clipping
       ↓
Band Extraction
       ↓
Preprocessing
       ↓
Raster Combination
       ↓
Feature Generation
       ↓
Classification
       ↓
Accuracy Assessment
       ↓
Analysis
       ↓
Visualization
       ↓
Automated Reporting