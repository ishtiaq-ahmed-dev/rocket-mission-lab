import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
const proxy={'/api':{target:'http://127.0.0.1:8010',ws:true,rewrite:(p:string)=>p.replace(/^\/api/,'')}};
export default defineConfig({plugins:[react(),tailwindcss()],server:{port:5180,strictPort:true,proxy},preview:{port:5180,strictPort:true,proxy}});
