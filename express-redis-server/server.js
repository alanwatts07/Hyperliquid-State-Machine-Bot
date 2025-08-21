const express = require('express');
const { createClient } = require('redis');

const app = express();
app.use(express.json());

const client = createClient();

client.on('error', (err) => console.log('Redis Client Error', err));

app.post('/signal', async (req, res) => {
    try {
        const signal = req.body;
        console.log('Received signal:', signal);

        // Publish the signal to the 'trading-signals' channel
        await client.publish('trading-signals', JSON.stringify(signal));

        res.status(200).send('Signal received and published');
    } catch (error) {
        console.error('Error publishing signal:', error);
        res.status(500).send('Error publishing signal');
    }
});

const startServer = async () => {
    await client.connect();
    app.listen(3000, () => {
        console.log('Server is running on port 3000');
    });
};

startServer();