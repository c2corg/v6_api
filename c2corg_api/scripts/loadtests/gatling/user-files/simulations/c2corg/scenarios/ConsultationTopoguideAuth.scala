package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._

class ConsultationTopoguideAuth extends Simulation {

  val httpProtocol = http
    .inferHtmlResources(C2corgConf.black_list, WhiteList())
    .acceptHeader("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
    .acceptEncodingHeader("gzip, deflate")

  val scn = scenario("ConsultationTopoguideAuth")
    .exec(Homepage.init)
    .pause(1)
    .exec(Auth.login)
    .pause(10)
    .exec(Homepage.initAuth)
    .pause(8)
    .exec(Homepage.browseAuth)
    .pause(4)
    .exec(Outing.view)
    .pause(9)
    .exec(Route.view)
    .pause(10)
    .exec(Image.upload)
    .pause(5)
    .exec(Outing.add)

  val numUsers = Integer.getInteger("users", 100)
  val rampSec = Integer.getInteger("ramp", 300)

  setUp(scn.inject(rampUsers(numUsers) over (rampSec seconds))).protocols(httpProtocol)

}
