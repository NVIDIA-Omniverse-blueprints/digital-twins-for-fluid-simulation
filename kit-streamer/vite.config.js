import { defineConfig } from 'vite';

export default defineConfig({
    build: {
        lib: {
            entry: './index.js',
            name: 'KitStreamer',
            fileName: 'kit-streamer',
            formats: ['iife'],
        },
        outDir: '../trame-app/static',
        emptyOutDir: false,
    },
});
