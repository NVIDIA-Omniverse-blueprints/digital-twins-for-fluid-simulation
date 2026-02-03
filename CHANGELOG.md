# Changelog

## Version 2026.01
### Added
* Adds support for Blackwell GPUs
* Adds ability to configure CUDA devices via .env

### Changed
* Updated versioning scheme for blueprint to YYYY.MM
* Updated Aeronim to 2.0
* Updated Kit version to 109.0.1
* Updated Omniverse base container image
* Updated webrtc-streaming-library to 5.6.0
* Updated `.kit`file renderer settings to reduce ghosting artifacts with real-time renderer

### Fixed
* Fixed broken links in README docs

## Removed
* Removed local host networking requirement for container communication

### Known Issue
* Visual artifacts for flow and streamlines may exist depending on `.kit` file renderer and viewport settings
* Renderer outputs can show inconsistent lighting results when using clear coat materials

## Version 2025.03 (previously 1.0.0)
* Initial Release.
