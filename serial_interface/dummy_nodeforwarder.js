/*
NodeForwader: an serial to http proxy driven by ghetto get calls
requirements
   -- serialport -> npm install serialport
   -- express -> npm install express
   -- sleep -> npm install sleep
   -- socket.io -> npm install socket.io
   -- cors -> npm install cors

to start: node nodeforwader.js [HTTP PORT] [SERIAL PORT] [BAUD] [BUFFER LENGTH]
to read: http://[yourip]:[spec'd port]/read/  -> returns the last [BUFFER LENGTH] bytes from the serial port as a string
to write: http://[yourip]:[spec'd port]/write/[YOUR STRING HERE]

what will probably create farts/list of things to deal with later if I need to:
- returning characters that html has issues with
- spaces in the url

*/

parts = process.argv

if (parts.length < 6) {
	console.log("usage: node nodeforwader.js [HTTP PORT] [SERIAL PORT] [BAUD] [BUFFER LENGTH] [LOG=YES optional]")
	process.exit(1);
}

else {
	console.log(parts);
	hp = parts[2]
	sp = parts[3]
	baud = parseInt(parts[4])
	blen = parseInt(parts[5])
}

var logfile = false;
if (parts.length == 7) logfile = true;

var bodyParser = require('body-parser');
var app = require('express')();
// var http = require('http').Server(app);
// var io = require('socket.io')(http);
var cors = require('cors')
// const createCsvWriter = require('csv-writer').createArrayCsvWriter;
// const csvWriter = createCsvWriter({
//     header: ['Time (seconds since epoch)', 'Pump A duty (0-255)', 'Pump B Duty (0-255)','Pump A rpm', 'Pump B rpm'],
//     path: 'C:\\Users\\Thoma\\Documents\\Engineering\\Part C\\4YP\\Logs' + (new Date().getTime()/1000).toString() + '.csv'
// });
var server = app.listen(hp, () => console.log("server started"));

var connections = []

server.on('connection', connection => {
    connections.push(connection);
    connection.on('close', () => connections = connections.filter(curr => curr !== connection));
});

function shutDown() {
    console.log('Received kill signal, shutting down gracefully');
    server.close(() => {
        console.log('Closed out remaining connections');
        process.exit(0);
    });

    setTimeout(() => {
        console.error('Could not close connections in time, forcefully shutting down');
        process.exit(1);
    }, 10000);

    connections.forEach(curr => curr.end());
    setTimeout(() => connections.forEach(curr => curr.destroy()), 5000);
}




// var SerialPort = require('serialport').SerialPort; //per ak47 fix
// var serialPort = new SerialPort(
// 	{
// 		path: sp,
// 		baudRate: baud
// 	});


// serialPort.on("open", function () {
// 	console.log('open');

// });

// serialPort.on("close", function () {
// 	console.log('closed, reopening');
// 	var serialPort = new SerialPort(sp,
// 		{
// 			baudrate: baud
// 		});

// });



//sleep for 3 seconds for arduino serialport purposes
console.log('Sleeping three seconds for microcontroller...')
var waitTill = new Date(new Date().getTime() + 3000);
while(waitTill > new Date()){}
console.log("open")

//On Data fill a circular buf of the specified length
buf = ""

//last heard
var lh = 0;
// serialPort.on('data', function (data) {
// 	data = data.toString('binary')
// 	lh = new Date().getTime()
// 	data = lh/1000 + ',' + data
// 	records = data.replace('\r\n','').split(',')
// 	records = [records] //needed for csvwriter

// 	if (logfile) {

// 		csvWriter.writeRecords(records).then(() => console.log(data));
// 	}

// 	buf += data.toString('binary')
// 	if (buf.length > blen) buf = buf.substr(buf.length - blen, buf.length)
// 	io.emit('data', data.toString('utf8'));

// });

//Enable Cross Site Scripting
app.use(cors())

//Allows us to rip out data?
app.use(bodyParser.urlencoded({ extended: true }));
app.use(bodyParser.json());


//Write to serial port
app.get('/write/*', function (req, res) {
	toSend = req.originalUrl.replace("/write/", "")
	toSend = decodeURIComponent(toSend);
	console.log(toSend)
	// serialPort.write(Buffer.from(toSend))
	res.send(toSend)
});

app.get('/writecf/*', function (req, res) {
	toSend = req.originalUrl.replace("/writecf/", "")
	toSend = decodeURIComponent(toSend);
	console.log(toSend)
	// serialPort.write(Buffer.from(toSend + "\r\n"))
	res.send(toSend)
});

app.post('/write', function (req, res) {
	x = req.body
	toSend = x
	console.log(toSend)

	// serialPort.write(Buffer.from(toSend['payload']))
	res.send(toSend)
});


//Show Last Updated
app.get('/lastread/', function (req, res) {
	lhs = lh.toString();
	console.log(lhs)
	res.send(lhs)
});


//read buffer
app.get('/read/', function (req, res) {
	// res.send(buf)
	lh = new Date().getTime()
	outstr = Array.from({length: 6}, () => Math.floor(Math.random() * 12300)).join(",");
	res.send(outstr)
});


//weak interface
app.get('/', function (req, res) {
	res.sendFile(__dirname + '/readout.html');
});


app.get('/readout/', function (req, res) {
	res.sendFile(__dirname + '/readout.html');
});

// //sockets
// io.on('connection', function (socket) {
// 	io.emit('data', buf)
// 	socket.on('input', function (msg) {
// 		//console.log('message: ' + msg);
// 		serialPort.write(msg + "\r\n")

// 	});
// });

app.get('/stop/',function (req, res){
	res.send("Server shut down")
	shutDown()
});