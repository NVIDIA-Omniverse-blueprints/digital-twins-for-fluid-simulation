# omni.rtwt.inference

Real-time wind tunnel surrogate-model inference and native Kit-CAE 3 result publication.

`InferenceOperator` resolves a request from memory, the optional `.npz` disk cache, or Triton. Each
Triton wire output is mapped by an `RtwtResultFieldSelectionAPI:<wire-output>` instance to:

- one target `OmniSciDataset`; and
- one paired `OmniSciFieldAPI:<fieldName>` / `OmniSciArrayAPI:<fieldName>` instance on that dataset.

The extension publishes all fields for a dataset as one cache revision through
`RtwtInferenceResultsAPI`. Its registered SimData commands expose the cached NanoVDB buffers as
`warp_simdata.Field` objects, so `omni.cae.viz` operators consume live, cached, and comparison
results through the same active Kit-CAE 3 path.

The result dataset must compose `OmniSciVtkImageDataAPI`, normally by referencing the inference
domain. Cached RTWT NanoVDB fields must use `association = "node"`; the bridge rejects unspecified,
element, and cell associations.

There is no RTWT Data Delegate and no per-field `CaeFieldArray` prim. New result fields belong on
the result `OmniSciDataset` and must be declared in both the stage and the workflow manifest.
