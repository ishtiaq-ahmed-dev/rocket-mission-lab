import {it,expect} from 'vitest';
import {terrainHeight,shoreline} from './terrain';
it('keeps the entire road and engineered complex on one unbroken surface',()=>{for(let x=-330;x<=0;x+=5){expect(terrainHeight(x,0)).toBeCloseTo(0);}for(const [x,z] of [[-280,-70],[-135,72],[-135,-72],[0,0]])expect(terrainHeight(x,z)).toBeCloseTo(0);});
it('coastline has a continuous slope into sea rather than floating land edges',()=>{for(let z=-1000;z<=1000;z+=40){const x=shoreline(z);expect(terrainHeight(x,z)).toBe(-4);expect(Math.abs(terrainHeight(x-1,z)-terrainHeight(x,z))).toBeLessThan(.05);}});
