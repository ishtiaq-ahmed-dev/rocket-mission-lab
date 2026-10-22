/** Custom effects must write the same logarithmic depth as standard materials
 * when a close nozzle and a planetary horizon share one camera frustum. */
export const depthVertex=(shader:string)=>`#include <logdepthbuf_pars_vertex>\n${shader.replace(/}\s*$/, '\n#include <logdepthbuf_vertex>\n}')}`;
export const depthFragment=(shader:string)=>`#include <logdepthbuf_pars_fragment>\n${shader.replace('void main(){','void main(){\n#include <logdepthbuf_fragment>\n')}`;
