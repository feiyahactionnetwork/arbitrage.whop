'use client';

const { Cloudinary } = require('cloudinary-core');

// Cloudinary configuration for image optimization
const cloudinary = new Cloudinary({
  cloud_name: 'your_cloud_name',
  secure: true,
});

module.exports = {
  images: {
    domains: ['res.cloudinary.com'],
    loader: 'cloudinary',
    path: 'https://res.cloudinary.com/your_cloud_name/',
  },
  async headers() {
    return [
      {
        // Apply security headers
        source: '/(.*)',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: 'default-src self; img-src https:; script-src https:; style-src https:;',
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'X-XSS-Protection',
            value: '1; mode=block',
          },
        ],
      },
    ];
  },
};
