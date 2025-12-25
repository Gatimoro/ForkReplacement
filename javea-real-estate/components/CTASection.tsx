export default function CTASection() {
  return (
    <section className="py-20 gradient-border">
      <div className="container mx-auto px-4">
        <div className="max-w-3xl mx-auto text-center space-y-6">
          <h2 className="text-4xl md:text-5xl font-bold">
            ¿Tienes una propiedad en{' '}
            <span className="gradient-text">Jávea</span>?
          </h2>

          <p className="text-xl text-muted">
            Publica tu propiedad de forma gratuita y conecta con miles de
            compradores potenciales
          </p>

          <div className="pt-4">
            <button className="px-8 py-4 bg-white text-background font-semibold rounded-lg hover-glow transition-all text-lg">
              Publicar gratis
            </button>
          </div>

          <div className="pt-8 flex flex-wrap justify-center gap-8 text-sm text-muted">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-primary rounded-full" />
              <span>Sin comisiones</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-primary rounded-full" />
              <span>Publicación inmediata</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-primary rounded-full" />
              <span>Máxima visibilidad</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
