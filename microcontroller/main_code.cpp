bool modified[numPumps];

int nameIndex(char name){
  for (int i=0;i<numPumps;i++){
    if (pumps[i].name == name){
      return i;
    }
  }
}

bool checkName(char name){
  for (int i=0;i<numPumps;i++){
    if (pumps[i].name == name){
      return true;
    }
  }
  return false;
}

void readOneCommand(){
  // read from the serial until ">" and set the duty of the corresponding pump

  char nextChar = '\0';
  int nextInt = (int) nextChar;
  char name = '\0';
  bool readDuty = false;
  String command = "";
  while (Serial.available() > 0 && nextChar != endChar){
    if (nextChar == ','){
      // "," separates name and duty, so next section of the serial command is the duty
      readDuty = true;
      // check if name is in the list of names!
      if (!checkName(name)){
        return;
      }
    }else if (readDuty){
      // ensure the next characters are digits
      if (isDigit(nextInt)){
        command += nextChar;
      }else{
        return;
      }
    }else if (nextChar != '\0'){
      // for now, the name is only a single char, so if not reading duty or ',', then the char is the name
      name = nextChar;
    }
    // read the serial buffer, both as an int and cast to char
    nextInt = Serial.read();
    nextChar = (char) nextInt;
  }
  // loop exited: either command is complete or the serial buffer is empty
  if (nextChar == endChar){
    // command complete, save the duty to the pump

    // get the index of the pump from its name
    int index = nameIndex(name);
    PumpConnection& pmp = pumps[index];
    // save the new duty to the pump object
    pmp.duty = command.toInt();
    // mark the pump as modified
    modified[index] = true;
  }
  return;
}

void performCommands(){
  // write duty to the pwm pin for each PumpConnection
  for (int i = 0; i<numPumps; i++){
    if (modified[i]){
      // pump duty has been modified, so it needs writing
      PumpConnection& pmp = pumps[i];
      // write the pump's duty to the pump's pwm pin
      analogWrite(pmp.pwm,pmp.duty);
      modified[i] = false;
    }
  }
}

void writeSpeeds(){
  // read the current time and calculate
  uint32_t currentTime = millis();
  unsigned long elapsedTime;
  if (currentTime>=recentMillis){
    elapsedTime = currentTime - recentMillis;
  }else{
    // millis() has overflowed!!
    recentMillis = currentTime;
    elapsedTime = 0;
    // reset all counts
    for (int i=0;i<numPumps;i++){
      pumps[i].detach_isr();
      pumps[i].resetCount();
    }
    for (int j=0;j<numPumps;j++){
      pumps[j].attach_isr();
    }
  }  

  // check if enough time has passed since last speed calc
  if (elapsedTime >= serialWritePeriod){
    
    // set the most recent reading time to the current time
    // Serial.println("EDITING");
    recentMillis = currentTime;

    unsigned int speeds[numPumps];
    for (int i=0;i<numPumps;i++){
      // pause isr rotation counts while sending
      pumps[i].detach_isr();
    }
    // output the speeds for each pump to serial
    for (int j=0;j<numPumps;j++){
      // calculate speed in rpm
      unsigned long rpm = (pumps[j].rotationCount() * 1000 * 60)/elapsedTime;
      sendSpeed(j,rpm);
    }
    Serial.print('\n');
    for (int k=0;k<numPumps;k++){
      pumps[k].resetCount();
      pumps[k].attach_isr();
    }
  }
}

void setup() {
  // establish serial connection
  Serial.begin(9600);
  
  // initialise every pump
  for (int i;i<numPumps;i++){
    pumps[i].initialise(isrFuns[i]);
    //initialise modification tracker for pump i
    modified[i] = false;
  }
}

void loop() {
  while (Serial.available()>0){
    readOneCommand();
  }
  delay(loopdelay);
  performCommands();
  writeSpeeds();
}