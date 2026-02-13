// See: https://github.com/Chainlit/chainlit/issues/1887

const RealContext = window.AudioContext || window.webkitAudioContext;
window.AudioContext = function (opts = {}) {
  // Firefox can't override the microphone's sample rate
  if (navigator.userAgent.includes("Firefox")) {
    // console.debug("Removing sample rate");
    delete opts.sampleRate;
    return new RealContext(opts);
  } else {
    const newSampleRate = 16000;
    // console.debug(
    //   `Overriding sample rate: ${opts.sampleRate} => ${newSampleRate}`,
    // );
    opts.sampleRate = newSampleRate;
    return new RealContext(opts);
  }
};
