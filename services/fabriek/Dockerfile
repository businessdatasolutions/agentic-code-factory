# Het volgscherm van de code factory, als opgenomen run (BUILDPLAN — werkwijze/).
#
# **Waarom hier geen repository in zit.** Het scherm meet normaal de git-toestand
# van elke worktree. In een container is er geen werkkopie en er valt niets aan
# te sturen, dus draait hij in opnamestand: hij leest één bevroren run en weigert
# elke schrijfroute. De inhoud is een échte run en geen opgemaakte, en de pagina
# zegt dat bovenaan — een scherm dat eruitziet als live en het niet is, is erger
# dan geen scherm.
#
# Eén laag, geen build-stap, geen afhankelijkheden: het scherm is één .mjs-bestand
# op de ingebouwde modules van node. Dezelfde vorm als scripts/beheer-lokaal.mjs.

FROM node:24-slim

WORKDIR /app

# De opname en het scherm. `config.json` moet mee: het scherm leest daaruit de
# drempels voor de waarschuwingen, en dat is dezelfde bron als de manager
# gebruikt — twee kopieën van die lijst zou betekenen dat het scherm iets anders
# bewaakt dan er is afgedwongen.
COPY scripts/volgscherm.mjs ./scripts/volgscherm.mjs
COPY werkwijze/config.json ./werkwijze/config.json
COPY werkwijze/opname ./werkwijze/opname

ENV FABRIEK_SNAPSHOT=1
ENV PORT=8080
EXPOSE 8080

# Cloud Run geeft de poort via $PORT; het scherm leest die vóór zijn argumenten.
CMD ["node", "scripts/volgscherm.mjs", "werkwijze/opname"]
