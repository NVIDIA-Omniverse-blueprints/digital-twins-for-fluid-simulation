# Changelog

## [Unreleased]
### Added
- Offline cache for inference results. New settings: `offline_mode`,
  `generate_if_missing`, `offline_cache_dir`.
- Native Warp SimData commands for discovering and reading inference fields from an
  `RtwtInferenceResultsAPI` `OmniSciDataset`.

### Changed
- Publish all fields targeting one result dataset under a single atomic revision.
- Map Triton wire outputs to OmniSci field instance names instead of per-field prims.

### Removed
- The dependency on the RTWT predicted-field Data Delegate.

## [1.0.0] - 2025-01-01
### Added
- Initial empty extension.
