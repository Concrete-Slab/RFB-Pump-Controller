#include <math.h>
#define startChar '<'
#define endChar '>'
#define serialWritePeriod 1000
#define loopdelay 10

typedef void (*ISRPointer)();

class PumpConnection{
  private:
    ISRPointer _isrWrapper;
    volatile unsigned int _rotationCount;
  public:
    const unsigned int pwm;
    const int tacho; // tacho<0 if pump does not have a tachometer
    const char name;
    unsigned int duty = 0;
    unsigned int speed = 0;
    PumpConnection(unsigned int pwm_pin, int tacho_pin, char pump_name) : pwm(pwm_pin), tacho(tacho_pin), name(pump_name){}

    void isr(){
      _rotationCount += 1;
    }
    void initialise(ISRPointer isrWrapper){
      pinMode(pwm,OUTPUT);
      pinMode(tacho,INPUT);
      analogWrite(pwm,0);
      this->_isrWrapper = isrWrapper;
      attach_isr();
    }
    bool hasTacho() const {
      return (tacho>=0);
    }
    unsigned int rotationCount() const {
      return _rotationCount;
    }
    void resetCount(){
      _rotationCount = 0;
    }
    void attach_isr(){
      if (hasTacho() && _isrWrapper){
        attachInterrupt(digitalPinToInterrupt(tacho), _isrWrapper, FALLING);
      }
    }
    void detach_isr(){
      if (hasTacho()){
        detachInterrupt(digitalPinToInterrupt(tacho));
      }
    }
};

unsigned long recentMillis = 0;