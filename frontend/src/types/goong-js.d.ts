declare module "@goongmaps/goong-js" {
  export interface MapOptions {
    container: HTMLElement | string;
    style: string;
    center?: [number, number];
    zoom?: number;
  }

  export class Map {
    constructor(options: MapOptions);
    remove(): void;
    setCenter(center: [number, number]): void;
    setZoom(zoom: number): void;
    on(event: string, cb: () => void): void;
    addControl(control: unknown): void;
  }

  export class Marker {
    constructor(options?: { color?: string });
    setLngLat(lngLat: [number, number]): this;
    addTo(map: Map): this;
    remove(): this;
  }

  export class NavigationControl {
    constructor();
  }

  interface GoongJS {
    accessToken: string;
    Map: typeof Map;
    Marker: typeof Marker;
    NavigationControl: typeof NavigationControl;
  }

  const goongjs: GoongJS;
  export default goongjs;
}
