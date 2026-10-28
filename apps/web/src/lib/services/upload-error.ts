/** Failed files can be retried without uploading successful files twice. */
export class UploadBatchError extends Error {
  constructor(message: string, readonly failedFiles: File[]) { super(message); }
}
