export interface Property {
  id: string;
  type: 'house' | 'investment' | 'plot';
  title: string;
  price: number;
  location: string;
  image: string;
  badge?: string;
  specs: {
    bedrooms?: number;
    bathrooms?: number;
    size: number;
    plotSize?: number;
    roi?: number;
    zone?: string;
    buildable?: boolean;
  };
}

// Sample properties for "Casas y Pisos"
export const houses: Property[] = [
  {
    id: 'h1',
    type: 'house',
    title: 'Villa moderna con vistas al mar',
    price: 450000,
    location: 'Jávea, Portichol',
    image: 'https://images.unsplash.com/photo-1613490493576-7fde63acd811?w=800&h=500&fit=crop',
    badge: 'Destacado',
    specs: {
      bedrooms: 4,
      bathrooms: 3,
      size: 220,
    },
  },
  {
    id: 'h2',
    type: 'house',
    title: 'Apartamento en primera línea',
    price: 320000,
    location: 'Jávea, Arenal',
    image: 'https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=800&h=500&fit=crop',
    badge: 'Nuevo',
    specs: {
      bedrooms: 2,
      bathrooms: 2,
      size: 95,
    },
  },
  {
    id: 'h3',
    type: 'house',
    title: 'Casa de campo tradicional',
    price: 890000,
    location: 'Jávea, Gràcia',
    image: 'https://images.unsplash.com/photo-1564013799919-ab600027ffc6?w=800&h=500&fit=crop',
    specs: {
      bedrooms: 5,
      bathrooms: 4,
      size: 380,
      plotSize: 2000,
    },
  },
  {
    id: 'h4',
    type: 'house',
    title: 'Bungalow cerca del puerto',
    price: 275000,
    location: 'Jávea, Puerto',
    image: 'https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?w=800&h=500&fit=crop',
    specs: {
      bedrooms: 3,
      bathrooms: 2,
      size: 110,
    },
  },
  {
    id: 'h5',
    type: 'house',
    title: 'Villa de lujo con piscina',
    price: 510000,
    location: 'Jávea, Cap Martí',
    image: 'https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=800&h=500&fit=crop',
    badge: 'Destacado',
    specs: {
      bedrooms: 4,
      bathrooms: 3,
      size: 285,
      plotSize: 1200,
    },
  },
  {
    id: 'h6',
    type: 'house',
    title: 'Ático con terraza panorámica',
    price: 650000,
    location: 'Jávea, Balcón al Mar',
    image: 'https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?w=800&h=500&fit=crop',
    specs: {
      bedrooms: 3,
      bathrooms: 2,
      size: 140,
    },
  },
];

// Sample properties for "Oportunidades de Inversión"
export const investments: Property[] = [
  {
    id: 'i1',
    type: 'investment',
    title: 'Edificio de apartamentos turísticos',
    price: 1200000,
    location: 'Jávea, Arenal',
    image: 'https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?w=800&h=500&fit=crop',
    badge: 'Alta Rentabilidad',
    specs: {
      bedrooms: 8,
      bathrooms: 8,
      size: 450,
      roi: 8,
    },
  },
  {
    id: 'i2',
    type: 'investment',
    title: 'Local comercial en zona turística',
    price: 385000,
    location: 'Jávea, Centro',
    image: 'https://images.unsplash.com/photo-1497366216548-37526070297c?w=800&h=500&fit=crop',
    specs: {
      size: 180,
      roi: 6,
    },
  },
  {
    id: 'i3',
    type: 'investment',
    title: 'Complejo de villas en construcción',
    price: 2500000,
    location: 'Jávea, Tosalet',
    image: 'https://images.unsplash.com/photo-1600047509807-ba8f99d2cdde?w=800&h=500&fit=crop',
    badge: 'Preventa',
    specs: {
      bedrooms: 15,
      bathrooms: 15,
      size: 950,
      roi: 10,
    },
  },
  {
    id: 'i4',
    type: 'investment',
    title: 'Apartamentos de obra nueva',
    price: 280000,
    location: 'Jávea, Pinosol',
    image: 'https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=800&h=500&fit=crop',
    badge: 'Nuevo',
    specs: {
      bedrooms: 2,
      bathrooms: 2,
      size: 85,
      roi: 7,
    },
  },
  {
    id: 'i5',
    type: 'investment',
    title: 'Hotel boutique en el casco antiguo',
    price: 1850000,
    location: 'Jávea, Casco Antiguo',
    image: 'https://images.unsplash.com/photo-1566073771259-6a8506099945?w=800&h=500&fit=crop',
    specs: {
      bedrooms: 12,
      bathrooms: 12,
      size: 650,
      roi: 9,
    },
  },
  {
    id: 'i6',
    type: 'investment',
    title: 'Restaurante con licencia activa',
    price: 420000,
    location: 'Jávea, Puerto',
    image: 'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=800&h=500&fit=crop',
    specs: {
      size: 220,
      roi: 8,
    },
  },
];

// Sample properties for "Parcelas"
export const plots: Property[] = [
  {
    id: 'p1',
    type: 'plot',
    title: 'Parcela edificable con vistas',
    price: 195000,
    location: 'Jávea, Adsubia',
    image: 'https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=800&h=500&fit=crop',
    badge: 'Oportunidad',
    specs: {
      size: 1200,
      buildable: true,
      zone: 'Residencial',
    },
  },
  {
    id: 'p2',
    type: 'plot',
    title: 'Terreno urbanizable costero',
    price: 340000,
    location: 'Jávea, Cap de la Nao',
    image: 'https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=800&h=500&fit=crop',
    specs: {
      size: 800,
      buildable: true,
      zone: 'Residencial Premium',
    },
  },
  {
    id: 'p3',
    type: 'plot',
    title: 'Parcela rústica con olivos',
    price: 125000,
    location: 'Jávea, Rafol',
    image: 'https://images.unsplash.com/photo-1516905041604-7935af78f572?w=800&h=500&fit=crop',
    specs: {
      size: 2000,
      buildable: false,
      zone: 'Agrícola',
    },
  },
  {
    id: 'p4',
    type: 'plot',
    title: 'Terreno urbano céntrico',
    price: 280000,
    location: 'Jávea, Centro',
    image: 'https://images.unsplash.com/photo-1472214103451-9374bd1c798e?w=800&h=500&fit=crop',
    badge: 'Exclusivo',
    specs: {
      size: 600,
      buildable: true,
      zone: 'Residencial',
    },
  },
  {
    id: 'p5',
    type: 'plot',
    title: 'Gran parcela con proyecto incluido',
    price: 520000,
    location: 'Jávea, Balcón al Mar',
    image: 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800&h=500&fit=crop',
    badge: 'Con Proyecto',
    specs: {
      size: 1500,
      buildable: true,
      zone: 'Residencial Premium',
    },
  },
  {
    id: 'p6',
    type: 'plot',
    title: 'Parcela en zona tranquila',
    price: 165000,
    location: 'Jávea, Pueblo',
    image: 'https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?w=800&h=500&fit=crop',
    specs: {
      size: 950,
      buildable: true,
      zone: 'Residencial',
    },
  },
];

export const allProperties: Property[] = [...houses, ...investments, ...plots];
