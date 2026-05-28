# Changelog

## v0.4.0 (2026-05-28)

### Breaking Changes
- Remove global state management in favor of dependency injection
- Remove backward-compatibility globals from dataset_manager.py
- MCPContext now required for MCP tools

### New Features
- Add full dataset validation in UI (Validate button in header)
- Add parent-child relationship validation in MCP entity creation
- Add DatasetManagerFactory for managing dataset managers per AppState

### Bug Fixes
- Fix state synchronization between MCP and UI (root cause of dataset loading bugs)
- Fix graph not updating when MCP creates entities
- Fix Explorer and Spec Builder routing

### MIAPPE Profiles
- Add events field to ObservationUnit in MIAPPE 1.1 and 1.2 (matches original spec: "0+ per study/observation unit")
- MIAPPE-HTP already had this field

### Internal
- Create MCPContext dataclass for explicit dependency injection
- Centralize state management in app.state.mcp_context
- Update MCP tool prompts to emphasize importing only explicit data

## v0.3.9 (2026-05-28)

### Spec Builder Enhancements
- Add copy to clipboard button for YAML preview
- Add edit YAML directly feature with Apply/Cancel
- Redesign YAML preview modal with cleaner styling
- Unify all modals with dark theme and larger size
- Fix button alignment in preview header
- Remove non-functional +Relationship button

### MetaboLights Profile
- Fix validation rules to reference merged Assay entity
- Add multi-technique study support documentation
- Clarify when polymorphism is needed vs enum-based differentiation

### CropXR Profile
- Create unified CropXR v1.0 profile with assay-type discriminator
- Combine phenotyping and sequencing into single profile
- Remove old fragmented profiles (cropxr-phenotyping, cropxr-sequencing)

### Documentation
- Add MetaboLights design discussion
- Update JupyterLab demo with MetaboLights example
- Document entity relationships (nested vs reference)

## v0.3.8 and earlier

See git history for previous changes.
