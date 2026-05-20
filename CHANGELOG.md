# Changelog

## Version 2026.05
### Added
* Adds a lite Docker Compose profile for single-GPU, offline operation using pre-baked inference results
* Adds pre-baked inference cache files for supported velocity and spoiler combinations
* Adds a custom AeroNIM container and `rtwt` Triton model wrapper for RTWT inference
* Adds a Trame-based web front-end for interacting with the streamed Kit application
* Adds a native AWS deployment option using AWS CDK under `deploy/aws-cdk`
* Adds a Helm chart for single-node Kubernetes deployments under `deploy/helm`
* Adds developer documentation for the RTWT architecture, control flow, and extension workflow
* Adds a top-level `kit-streamer` package for the Omniverse WebRTC streaming client
* Adds `kit-cae` as a submodule for shared Kit-CAE extensions and build tooling

### Changed
* Updated release version metadata to 2026.05
* Updated Kit SDK to 110.1.1
* Updated AeroNIM base image to 2.1.0
* Updated Omniverse base container image to 2025.2.0
* Updated Docker Compose to use standard and lite profiles for live-inference and cached-inference deployments
* Updated repository layout to use top-level Kit app, source, tools, stages, and data directories
* Updated README docs to compare lite and standard deployment requirements, controls, and limitations
* Updated deployment docs to cover Docker Compose, Kubernetes, and AWS paths

### Fixed
* Fixed RTWT extension package initialization files so Kit extensions load correctly from the top-level source tree
* Fixed Git ignore handling for generated build artifacts without excluding required Python package files
* Fixed cloud and VPN access guidance for host-public versus host-private networking
* Fixed runtime troubleshooting docs for NGC authentication, shader compilation, NVIDIA runtime setup, and Git LFS assets

### Removed
* Removed the legacy React `web-app` in favor of the Trame front-end
* Removed the legacy nested `kit-app` layout in favor of the top-level Kit application layout
* Removed obsolete development helper scripts in favor of `repo.sh`, Docker Compose profiles, and deployment-specific scripts

### Known Issue
* Lite profile ONLY serves the shipped cache combinations: four velocities by two spoiler states, with mirrors fixed on and rims fixed to standard
* AWS CDK deployment is intended for temporary validation and does not configure TLS or user authentication

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

### Removed
* Removed local host networking requirement for container communication

### Known Issue
* Visual artifacts for flow and streamlines may exist depending on `.kit` file renderer and viewport settings
* Renderer outputs can show inconsistent lighting results when using clear coat materials

## Version 2025.03 (previously 1.0.0)
* Initial Release.
