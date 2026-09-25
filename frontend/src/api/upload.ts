/** Multipart body for an UploadFile endpoint, through the typed client: mutate(fileBody(file)). */
export const fileBody = (file: File) => ({
  body: { file: file as unknown as string },
  bodySerializer: (body: { file: string }) => {
    const fd = new FormData();
    fd.append("file", body.file as unknown as Blob);
    return fd;
  },
});
