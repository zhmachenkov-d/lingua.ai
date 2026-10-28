# Marker Compose CPU spike — 2026-10-27

## OpenRAIL-M

Marker **code** is Apache-2.0; **model weights** use a modified AI Pubs OpenRAIL-M license (field-of-use): free for research, personal use, and startups under $5M funding/revenue. Commercial use of weights beyond that requires a Datalab commercial arrangement. Review the full terms before any non-personal deploy: https://github.com/datalab-to/marker/blob/master/MODEL_LICENSE

## Metrics

Job peak RSS (max observed, cgroup/process-tree): **19725.1 MiB**

| PDF | path | peak_rss_mb | mean_chars_per_page | printable_ratio | notes |
| --- | --- | ---: | ---: | ---: | --- |
| English_File_4th_edition_Beginner_Students_book.pdf | `failed` | 19725.1 | — | — | Marker failed: llamacpp server failed to become healthy at http://127.0.0.1:35085 within 600.0s. --- last llamacpp server logs --- warning: no usable GPU found, --gpu-layers option will be ignored warning: one possible reason is that llama.cpp was compiled without GPU support warning: consult docs/build.md for compilation instructions build: 7600 (be47fb928) with GNU 11.4.0 for Linux x86_64 system info: n_threads = 8, n_threads_batch = 8, total_threads = 16 system_info: n_threads = 8 (n_threads_batch = 8) / 16 \| init: using 15 threads for HTTP server start: binding port with default address family main: loading model srv load_model: loading model '/home/vscode/.cache/huggingface/hub/models--datalab-to--surya-ocr-2-gguf/snapshots/6a3a4c30e5e74446d4f8b6afd05b2f2da970f470/surya-2.gguf' common_init_result: fitting params to device memory, for bugs during this step try to reproduce them with -fit off, or provide --verbose logs if the bug only occurs with -fit on llama_model_load_from_file_impl: no backends are loaded. hint: use ggml_backend_load() or ggml_backend_load_all() to load a backend before calling this function llama_params_fit: encountered an error while trying to fit params to free device memory: failed to load model llama_params_fit: fitting params to free memory took 0.00 seconds llama_model_load_from_file_impl: no backends are loaded. hint: use ggml_backend_load() or ggml_backend_load_all() to load a backend before calling this function common_init_from_params: failed to load model '/home/vscode/.cache/huggingface/hub/models--datalab-to--surya-ocr-2-gguf/snapshots/6a3a4c30e5e74446d4f8b6afd05b2f2da970f470/surya-2.gguf' srv load_model: failed to load model, '/home/vscode/.cache/huggingface/hub/models--datalab-to--surya-ocr-2-gguf/snapshots/6a3a4c30e5e74446d4f8b6afd05b2f2da970f470/surya-2.gguf' srv operator(): operator(): cleaning up before exit... main: exiting due to model loading error /home/vscode/.local/bin/llama-server: error while loading shared libraries: libmtmd.so.0: cannot open shared object file: No such file or directory; PyMuPDF text layer empty |
| English_File_4th_edition_Beginner_Workbook.pdf | `failed` | 18412.6 | — | — | Marker failed: llamacpp server failed to become healthy at http://127.0.0.1:55469 within 600.0s. --- last llamacpp server logs --- warning: no usable GPU found, --gpu-layers option will be ignored warning: one possible reason is that llama.cpp was compiled without GPU support warning: consult docs/build.md for compilation instructions build: 7600 (be47fb928) with GNU 11.4.0 for Linux x86_64 system info: n_threads = 8, n_threads_batch = 8, total_threads = 16 system_info: n_threads = 8 (n_threads_batch = 8) / 16 \| init: using 15 threads for HTTP server start: binding port with default address family main: loading model srv load_model: loading model '/home/vscode/.cache/huggingface/hub/models--datalab-to--surya-ocr-2-gguf/snapshots/6a3a4c30e5e74446d4f8b6afd05b2f2da970f470/surya-2.gguf' common_init_result: fitting params to device memory, for bugs during this step try to reproduce them with -fit off, or provide --verbose logs if the bug only occurs with -fit on llama_model_load_from_file_impl: no backends are loaded. hint: use ggml_backend_load() or ggml_backend_load_all() to load a backend before calling this function llama_params_fit: encountered an error while trying to fit params to free device memory: failed to load model llama_params_fit: fitting params to free memory took 0.00 seconds llama_model_load_from_file_impl: no backends are loaded. hint: use ggml_backend_load() or ggml_backend_load_all() to load a backend before calling this function common_init_from_params: failed to load model '/home/vscode/.cache/huggingface/hub/models--datalab-to--surya-ocr-2-gguf/snapshots/6a3a4c30e5e74446d4f8b6afd05b2f2da970f470/surya-2.gguf' srv load_model: failed to load model, '/home/vscode/.cache/huggingface/hub/models--datalab-to--surya-ocr-2-gguf/snapshots/6a3a4c30e5e74446d4f8b6afd05b2f2da970f470/surya-2.gguf' srv operator(): operator(): cleaning up before exit... main: exiting due to model loading error /home/vscode/.local/bin/llama-server: error while loading shared libraries: libmtmd.so.0: cannot open shared object file: No such file or directory /home/vscode/.local/bin/llama-server: error while loading shared libraries: libmtmd.so.0: cannot open shared object file: No such file or directory; PyMuPDF text layer empty |

## Go / no-go

- [ ] go / no-go — owner after confirming peak RSS

## Install / run notes

Marker primary path raised during spike; recorded as evidence (not a silent primary switch). First error: Marker failed: llamacpp server failed to become healthy at http://127.0.0.1:35085 within 600.0s.
--- last llamacpp server logs ---
warning: no usable GPU found, --gpu-layers option will be ignored
warning: one possible reason is that llama.cpp was compiled without GPU support
warning: consult docs/build.md for compilation instructions
build: 7600 (be47fb928) with GNU 11.4.0 for Linux x86_64
system info: n_threads = 8, n_threads_batch = 8, total_threads = 16

system_info: n_threads = 8 (n_threads_batch = 8) / 16 | 

init: using 15 threads for HTTP server
start: binding port with default address family
main: loading model
srv    load_model: loading model '/home/vscode/.cache/huggingface/hub/models--datalab-to--surya-ocr-2-gguf/snapshots/6a3a4c30e5e74446d4f8b6afd05b2f2da970f470/surya-2.gguf'
common_init_result: fitting params to device memory, for bugs during this step try to reproduce them with -fit off, or provide --verbose logs if the bug only occurs with -fit on
llama_model_load_from_file_impl: no backends are loaded. hint: use ggml_backend_load() or ggml_backend_load_all() to load a backend before calling this function
llama_params_fit: encountered an error while trying to fit params to free device memory: failed to load model
llama_params_fit: fitting params to free memory took 0.00 seconds
llama_model_load_from_file_impl: no backends are loaded. hint: use ggml_backend_load() or ggml_backend_load_all() to load a backend before calling this function
common_init_from_params: failed to load model '/home/vscode/.cache/huggingface/hub/models--datalab-to--surya-ocr-2-gguf/snapshots/6a3a4c30e5e74446d4f8b6afd05b2f2da970f470/surya-2.gguf'
srv    load_model: failed to load model, '/home/vscode/.cache/huggingface/hub/models--datalab-to--surya-ocr-2-gguf/snapshots/6a3a4c30e5e74446d4f8b6afd05b2f2da970f470/surya-2.gguf'
srv    operator(): operator(): cleaning up before exit...
main: exiting due to model loading error
/home/vscode/.local/bin/llama-server: error while loading shared libraries: libmtmd.so.0: cannot open shared object file: No such file or directory; PyMuPDF text layer empty
