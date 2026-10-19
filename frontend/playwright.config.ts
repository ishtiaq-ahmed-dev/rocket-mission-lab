import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./e2e',use:{baseURL:'http://127.0.0.1:5180',viewport:{width:1440,height:1000},screenshot:'only-on-failure'},timeout:45000});
