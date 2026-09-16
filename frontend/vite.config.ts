import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()],base:'/static/app/',build:{outDir:'../static/app',emptyOutDir:true,manifest:true},server:{proxy:{'/api':'http://127.0.0.1:8000','/accounts':'http://127.0.0.1:8000'}}});
